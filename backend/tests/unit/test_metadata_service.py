"""
Unit tests for MetadataService

Tests:
- IMDb URL/ID extraction and validation
- Metadata fetching (success cases)
- Caching behavior
- Error classification (retryable vs permanent)
- Network error handling
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.services.metadata_service import MetadataService, CACHE_TTL_DAYS
from app.models.job import Metadata
from app.core.error_handling import RetryableError, PermanentError


class TestMetadataServiceExtraction:
    """Test IMDb ID extraction"""
    
    def test_extract_imdb_id_from_url(self):
        """Extract ID from valid IMDb URL"""
        url = "https://www.imdb.com/title/tt0111161/"
        imdb_id = MetadataService.extract_imdb_id(url)
        assert imdb_id == "tt0111161"
    
    def test_extract_imdb_id_from_url_with_query_params(self):
        """Extract ID from URL with query parameters"""
        url = "https://www.imdb.com/title/tt0111161/?ref_=tt_ov"
        imdb_id = MetadataService.extract_imdb_id(url)
        assert imdb_id == "tt0111161"
    
    def test_extract_imdb_id_directly(self):
        """Accept ID directly without URL"""
        imdb_id = MetadataService.extract_imdb_id("tt0111161")
        assert imdb_id == "tt0111161"
    
    def test_extract_imdb_id_invalid_format(self):
        """Reject invalid URL format"""
        with pytest.raises(PermanentError):
            MetadataService.extract_imdb_id("https://imdb.com/invalid")
    
    def test_extract_imdb_id_invalid_id_format(self):
        """Reject invalid ID format"""
        with pytest.raises(PermanentError):
            MetadataService.extract_imdb_id("invalid123")


class TestMetadataServiceCaching:
    """Test caching behavior"""
    
    @patch("app.services.metadata_service.BeautifulSoup")
    @patch("app.services.metadata_service.requests.get")
    def test_get_cached_metadata_found(self, mock_get, mock_soup):
        """Return cached metadata if found and not expired"""
        db = Mock(spec=Session)
        
        # Create mock metadata that's not expired
        metadata = Mock(spec=Metadata)
        metadata.expires_at = datetime.utcnow() + timedelta(days=5)
        metadata.cached_at = datetime.utcnow() - timedelta(days=5)
        metadata.refresh_count = 0
        
        db.query.return_value.filter.return_value.first.return_value = metadata
        
        result = MetadataService.get_cached_metadata(db, "tt0111161")
        
        assert result == metadata
        assert metadata.refresh_count == 1
        db.commit.assert_called_once()
    
    def test_get_cached_metadata_not_found(self):
        """Return None if metadata not found"""
        db = Mock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        
        result = MetadataService.get_cached_metadata(db, "tt0111161")
        
        assert result is None
    
    def test_get_cached_metadata_expired(self):
        """Return None if metadata has expired"""
        db = Mock(spec=Session)
        
        # Create mock metadata that's expired
        metadata = Mock(spec=Metadata)
        metadata.expires_at = datetime.utcnow() - timedelta(days=1)
        
        db.query.return_value.filter.return_value.first.return_value = metadata
        
        result = MetadataService.get_cached_metadata(db, "tt0111161")
        
        assert result is None


class TestMetadataServiceErrorHandling:
    """Test error classification"""
    
    @patch("app.services.metadata_service.requests.get")
    def test_scrape_imdb_404_permanent_error(self, mock_get):
        """404 should be PermanentError (movie not found)"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_get.return_value = mock_response
        
        with pytest.raises(PermanentError) as exc_info:
            MetadataService._scrape_imdb("tt9999999")
        
        assert "not found" in str(exc_info.value).lower()
    
    @patch("app.services.metadata_service.requests.get")
    def test_scrape_imdb_429_retryable_error(self, mock_get):
        """429 (rate limit) should be RetryableError"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        with pytest.raises(RetryableError) as exc_info:
            MetadataService._scrape_imdb("tt0111161")
        
        assert "rate limit" in str(exc_info.value).lower()
    
    @patch("app.services.metadata_service.requests.get")
    def test_scrape_imdb_503_retryable_error(self, mock_get):
        """503 (service unavailable) should be RetryableError"""
        mock_response = Mock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response
        
        with pytest.raises(RetryableError) as exc_info:
            MetadataService._scrape_imdb("tt0111161")
        
        assert "unavailable" in str(exc_info.value).lower()
    
    @patch("app.services.metadata_service.requests.get")
    def test_scrape_imdb_timeout_retryable_error(self, mock_get):
        """Timeout should be RetryableError"""
        import requests
        mock_get.side_effect = requests.Timeout()
        
        with pytest.raises(RetryableError) as exc_info:
            MetadataService._scrape_imdb("tt0111161")
        
        assert "timeout" in str(exc_info.value).lower()
    
    @patch("app.services.metadata_service.requests.get")
    def test_scrape_imdb_connection_error_retryable(self, mock_get):
        """Connection errors should be RetryableError"""
        import requests
        mock_get.side_effect = requests.ConnectionError("Connection failed")
        
        with pytest.raises(RetryableError) as exc_info:
            MetadataService._scrape_imdb("tt0111161")
        
        assert "network" in str(exc_info.value).lower()


class TestMetadataServiceFetching:
    """Test full metadata fetching"""
    
    @patch("app.services.metadata_service.MetadataService.get_cached_metadata")
    def test_fetch_imdb_returns_cached(self, mock_cached):
        """Return cached metadata if available"""
        db = Mock(spec=Session)
        
        cached_metadata = Mock(spec=Metadata)
        cached_metadata.imdb_id = "tt0111161"
        mock_cached.return_value = cached_metadata
        
        with patch.object(MetadataService, "_metadata_to_dict") as mock_to_dict:
            mock_to_dict.return_value = {"imdb_id": "tt0111161", "title": "Cached"}
            
            result = MetadataService.fetch_imdb("tt0111161", db)
        
        assert result["imdb_id"] == "tt0111161"
        mock_cached.assert_called_once()
    
    @patch("app.services.metadata_service.MetadataService.get_cached_metadata")
    @patch("app.services.metadata_service.MetadataService._store_in_cache")
    @patch("app.services.metadata_service.MetadataService._scrape_imdb")
    def test_fetch_imdb_scrapes_when_not_cached(self, mock_scrape, mock_store, mock_cached):
        """Scrape IMDb when metadata not cached"""
        db = Mock(spec=Session)
        mock_cached.return_value = None
        
        mock_scrape.return_value = {
            "imdb_id": "tt0111161",
            "title": "The Shawshank Redemption",
        }
        
        result = MetadataService.fetch_imdb("tt0111161", db)
        
        assert result["imdb_id"] == "tt0111161"
        mock_scrape.assert_called_once()
        mock_store.assert_called_once()
    
    @patch("app.services.metadata_service.MetadataService.get_cached_metadata")
    @patch("app.services.metadata_service.MetadataService._scrape_imdb")
    def test_fetch_imdb_force_refresh(self, mock_scrape, mock_cached):
        """Force refresh bypasses cache"""
        db = Mock(spec=Session)
        
        mock_scrape.return_value = {
            "imdb_id": "tt0111161",
            "title": "Fresh",
        }
        
        with patch.object(MetadataService, "_store_in_cache"):
            MetadataService.fetch_imdb("tt0111161", db, force_refresh=True)
        
        mock_cached.assert_not_called()
        mock_scrape.assert_called_once()


class TestMetadataServiceExtractors:
    """Test individual metadata extractors"""
    
    def test_extract_title(self):
        """Extract title from HTML"""
        from bs4 import BeautifulSoup
        html = '<h1 class="sc-uxip5d"><span>The Shawshank Redemption</span></h1>'
        soup = BeautifulSoup(html, "html.parser")
        
        title = MetadataService._extract_title(soup)
        assert title == "The Shawshank Redemption"
    
    def test_extract_rating(self):
        """Extract rating from HTML"""
        from bs4 import BeautifulSoup
        html = '<span data-testid="ratingValue">9.3</span>'
        soup = BeautifulSoup(html, "html.parser")
        
        rating = MetadataService._extract_rating(soup)
        assert rating == 9.3
    
    def test_extract_year(self):
        """Extract year from HTML"""
        from bs4 import BeautifulSoup
        html = '<span data-testid="releaseYear">(1994)</span>'
        soup = BeautifulSoup(html, "html.parser")
        
        year = MetadataService._extract_year(soup)
        assert year == 1994
    
    def test_extract_runtime(self):
        """Extract runtime from HTML"""
        from bs4 import BeautifulSoup
        html = '<li data-testid="runtime">142 min</li>'
        soup = BeautifulSoup(html, "html.parser")
        
        runtime = MetadataService._extract_runtime(soup)
        assert runtime == 142


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
