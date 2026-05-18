"""
MetadataService - Extract and cache IMDb metadata

This service handles:
1. Input validation (IMDb URL/ID)
2. Fetching metadata from IMDb
3. Caching with 30-day TTL
4. Error classification (retryable vs permanent)

Architecture:
- Uses BeautifulSoup for HTML parsing (IMDb is scrape-able)
- Caches in database with TTL (expires_at column)
- Classifies errors: Network timeouts are retryable, 404 is permanent
- Returns structured metadata for downstream stages

Error Handling:
- RetryableError: Network timeout, 429 (rate limit), 503 (service unavailable)
- PermanentError: 404 (not found), 400 (bad request), invalid URL format
"""
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import requests
from bs4 import BeautifulSoup

from app.core.error_handling import RetryableError, PermanentError
from app.models.job import Metadata

logger = logging.getLogger(__name__)

# IMDb URL patterns
IMDB_URL_PATTERN = r"https://www\.imdb\.com/title/(tt\d+)/?(?:\?.*)?$"
IMDB_ID_PATTERN = r"^tt\d+$"

# HTTP headers to mimic browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Cache TTL: 30 days
CACHE_TTL_DAYS = 30


class MetadataService:
    """Service for fetching and caching IMDb metadata"""
    
    @staticmethod
    def extract_imdb_id(url_or_id: str) -> str:
        """
        Extract IMDb ID from URL or return if already an ID.
        
        Args:
            url_or_id: Either a full IMDb URL or just the IMDb ID (tt0111161)
        
        Returns:
            IMDb ID (e.g., "tt0111161")
        
        Raises:
            PermanentError: Invalid URL or ID format
        """
        # If it looks like an ID already, validate and return
        if re.match(IMDB_ID_PATTERN, url_or_id):
            return url_or_id
        
        # Try to extract from URL
        match = re.match(IMDB_URL_PATTERN, url_or_id)
        if match:
            return match.group(1)
        
        # Invalid format
        raise PermanentError(
            f"Invalid IMDb URL or ID: {url_or_id}. "
            f"Expected format: https://www.imdb.com/title/tt0111161/ or tt0111161"
        )
    
    @staticmethod
    def get_cached_metadata(db: Session, imdb_id: str) -> Optional[Metadata]:
        """
        Get cached metadata if it exists and hasn't expired.
        
        Args:
            db: Database session
            imdb_id: IMDb ID (e.g., "tt0111161")
        
        Returns:
            Metadata object if found and not expired, else None
        """
        metadata = db.query(Metadata).filter(
            Metadata.imdb_id == imdb_id
        ).first()
        
        if not metadata:
            logger.debug(f"[{imdb_id}] No cached metadata found")
            return None
        
        # Check if expired
        if metadata.expires_at < datetime.utcnow():
            logger.info(f"[{imdb_id}] Cached metadata expired, will refresh")
            return None
        
        logger.info(f"[{imdb_id}] Using cached metadata (cached {(datetime.utcnow() - metadata.cached_at).days} days ago)")
        metadata.refresh_count += 1
        db.commit()
        return metadata
    
    @staticmethod
    def fetch_imdb(url_or_id: str, db: Session, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch IMDb metadata (from cache or API).
        
        Args:
            url_or_id: IMDb URL or ID
            db: Database session
            force_refresh: Ignore cache and fetch fresh data
        
        Returns:
            Dictionary with metadata:
            {
                "imdb_id": "tt0111161",
                "title": "The Shawshank Redemption",
                "plot": "...",
                "rating": 9.3,
                "genres": ["Drama"],
                "cast": [...],
                ...
            }
        
        Raises:
            PermanentError: Invalid URL, movie not found, invalid format
            RetryableError: Network timeout, rate limit, service unavailable
        """
        # Extract IMDb ID (validates format)
        imdb_id = MetadataService.extract_imdb_id(url_or_id)
        logger.info(f"[{imdb_id}] Fetching metadata")
        
        # Check cache first (unless force_refresh)
        if not force_refresh:
            cached = MetadataService.get_cached_metadata(db, imdb_id)
            if cached:
                return MetadataService._metadata_to_dict(cached)
        
        # Fetch from IMDb
        try:
            metadata = MetadataService._scrape_imdb(imdb_id)
            logger.info(f"[{imdb_id}] Successfully scraped: {metadata['title']}")
        except (RetryableError, PermanentError):
            raise
        except Exception as e:
            logger.error(f"[{imdb_id}] Unexpected error: {str(e)}")
            raise RetryableError(f"Failed to fetch metadata: {str(e)}")
        
        # Store in cache
        MetadataService._store_in_cache(db, imdb_id, metadata)
        
        return metadata
    
    @staticmethod
    def _scrape_imdb(imdb_id: str) -> Dict[str, Any]:
        """
        Scrape metadata from IMDb.
        
        Args:
            imdb_id: IMDb ID (e.g., "tt0111161")
        
        Returns:
            Dictionary with metadata
        
        Raises:
            PermanentError: 404 (not found), invalid response
            RetryableError: Network errors, rate limits, timeouts
        """
        url = f"https://www.imdb.com/title/{imdb_id}/"
        logger.debug(f"[{imdb_id}] Scraping: {url}")
        
        try:
            # Fetch with timeout
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            # Handle HTTP errors
            if response.status_code == 404:
                raise PermanentError(f"IMDb movie not found: {imdb_id}")
            
            if response.status_code == 429:
                raise RetryableError("Rate limit exceeded by IMDb")
            
            if response.status_code == 503:
                raise RetryableError("IMDb service temporarily unavailable")
            
            if response.status_code >= 400:
                raise PermanentError(f"IMDb returned {response.status_code}: {response.reason}")
            
            response.raise_for_status()
        
        except requests.Timeout:
            raise RetryableError(f"IMDb request timed out (10s)")
        except requests.ConnectionError as e:
            raise RetryableError(f"Network error connecting to IMDb: {str(e)}")
        except requests.RequestException as e:
            raise RetryableError(f"IMDb request failed: {str(e)}")
        
        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract metadata (best effort approach)
        metadata = {
            "imdb_id": imdb_id,
            "title": MetadataService._extract_title(soup),
            "plot": MetadataService._extract_plot(soup),
            "rating": MetadataService._extract_rating(soup),
            "release_year": MetadataService._extract_year(soup),
            "runtime_minutes": MetadataService._extract_runtime(soup),
            "genres": MetadataService._extract_genres(soup),
            "cast": MetadataService._extract_cast(soup),
            "poster_url": MetadataService._extract_poster(soup),
        }
        
        # Validate we got required fields
        if not metadata["title"]:
            raise PermanentError(f"Could not extract title from IMDb for {imdb_id}")
        
        logger.debug(f"[{imdb_id}] Extracted metadata: {metadata['title']}")
        return metadata
    
    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> Optional[str]:
        """Extract movie title"""
        # Try multiple selectors
        selectors = [
            "h1.sc-uxip5d span",  # Modern IMDb
            "h1",  # Fallback
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)
        return None
    
    @staticmethod
    def _extract_plot(soup: BeautifulSoup) -> str:
        """Extract plot summary"""
        selectors = [
            "p.sc-466bb906-2",  # Modern IMDb
            "div[data-testid='plot'] p",  # Newer version
            "p[class*='plot']",
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text:
                    return text
        return "Plot not available"
    
    @staticmethod
    def _extract_rating(soup: BeautifulSoup) -> Optional[float]:
        """Extract IMDb rating"""
        selectors = [
            "span[data-testid='ratingValue']",
            "span.sc-bde20123-1",
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                try:
                    return float(elem.get_text(strip=True))
                except ValueError:
                    pass
        return None
    
    @staticmethod
    def _extract_year(soup: BeautifulSoup) -> Optional[int]:
        """Extract release year"""
        # Look for year in various formats
        selectors = [
            "span[data-testid='releaseYear']",
            "a[href*='/year/']",
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                # Extract 4-digit year
                match = re.search(r"(\d{4})", text)
                if match:
                    return int(match.group(1))
        return None
    
    @staticmethod
    def _extract_runtime(soup: BeautifulSoup) -> Optional[int]:
        """Extract runtime in minutes"""
        selectors = [
            "li[data-testid='runtime']",
            "span[class*='runtime']",
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                # Extract number before 'min'
                match = re.search(r"(\d+)\s*min", text)
                if match:
                    return int(match.group(1))
        return None
    
    @staticmethod
    def _extract_genres(soup: BeautifulSoup) -> list:
        """Extract genres"""
        genres = []
        selectors = [
            "a[href*='/search/title/?genres=']",
            "span[data-testid='genres']",
        ]
        for selector in selectors:
            elems = soup.select(selector)
            for elem in elems:
                text = elem.get_text(strip=True)
                if text and text not in genres:
                    genres.append(text)
        return genres[:10]  # Limit to 10 genres
    
    @staticmethod
    def _extract_cast(soup: BeautifulSoup) -> list:
        """Extract cast members"""
        cast = []
        # Look for cast section
        selectors = [
            "a[data-testid='cast-name']",
            "a[href*='/name/nm']",
        ]
        for selector in selectors:
            elems = soup.select(selector)
            for elem in elems[:10]:  # Limit to 10 cast members
                name = elem.get_text(strip=True)
                if name:
                    cast.append(name)
            if cast:
                break
        return cast
    
    @staticmethod
    def _extract_poster(soup: BeautifulSoup) -> Optional[str]:
        """Extract poster image URL"""
        selectors = [
            "img[class*='poster']",
            "img[alt*='Poster']",
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                src = elem.get("src")
                if src and "imdb" in src:
                    return src
        return None
    
    @staticmethod
    def _store_in_cache(db: Session, imdb_id: str, metadata: Dict[str, Any]) -> None:
        """
        Store metadata in database cache.
        
        Args:
            db: Database session
            imdb_id: IMDb ID
            metadata: Metadata dictionary
        """
        expires_at = datetime.utcnow() + timedelta(days=CACHE_TTL_DAYS)
        
        # Check if already cached
        existing = db.query(Metadata).filter(Metadata.imdb_id == imdb_id).first()
        
        if existing:
            # Update existing cache
            existing.title = metadata["title"]
            existing.plot = metadata["plot"]
            existing.rating = metadata["rating"]
            existing.release_year = metadata["release_year"]
            existing.runtime_minutes = metadata["runtime_minutes"]
            existing.genres = metadata["genres"]
            existing.cast = metadata["cast"]
            existing.poster_url = metadata["poster_url"]
            existing.cached_at = datetime.utcnow()
            existing.expires_at = expires_at
            logger.info(f"[{imdb_id}] Updated cache")
        else:
            # Create new cache entry
            new_metadata = Metadata(
                imdb_id=imdb_id,
                title=metadata["title"],
                plot=metadata["plot"],
                rating=metadata["rating"],
                release_year=metadata["release_year"],
                runtime_minutes=metadata["runtime_minutes"],
                genres=metadata["genres"],
                cast=metadata["cast"],
                poster_url=metadata["poster_url"],
                cached_at=datetime.utcnow(),
                expires_at=expires_at,
            )
            db.add(new_metadata)
            logger.info(f"[{imdb_id}] Cached new metadata")
        
        db.commit()
    
    @staticmethod
    def _metadata_to_dict(metadata_obj: Metadata) -> Dict[str, Any]:
        """Convert Metadata ORM object to dictionary"""
        return {
            "imdb_id": metadata_obj.imdb_id,
            "title": metadata_obj.title,
            "plot": metadata_obj.plot,
            "rating": metadata_obj.rating,
            "release_year": metadata_obj.release_year,
            "runtime_minutes": metadata_obj.runtime_minutes,
            "genres": metadata_obj.genres or [],
            "cast": metadata_obj.cast or [],
            "poster_url": metadata_obj.poster_url,
        }


__all__ = ["MetadataService", "CACHE_TTL_DAYS"]
