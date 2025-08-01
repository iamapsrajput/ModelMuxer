# ModelMuxer (c) 2025 Ajay Rajput
# Licensed under Business Source License 1.1 – see LICENSE for details.

"""
Tests for the authentication and authorization system.
"""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, Request

from app.auth import APIKeyAuth


class TestAPIKeyAuth:
    """Test the API key authentication handler."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("app.auth.settings") as mock_settings:
            mock_settings.get_allowed_api_keys.return_value = ["sk-test-key-1", "sk-test-key-2"]
            self.auth = APIKeyAuth()

    def test_extract_api_key_bearer_format(self):
        """Test API key extraction from Bearer format."""
        authorization = "Bearer sk-test-key-123"
        api_key = self.auth.extract_api_key(authorization)

        assert api_key == "sk-test-key-123"

    def test_extract_api_key_direct_format(self):
        """Test API key extraction from direct format."""
        authorization = "sk-test-key-123"
        api_key = self.auth.extract_api_key(authorization)

        assert api_key == "sk-test-key-123"

    def test_extract_api_key_invalid_format(self):
        """Test API key extraction with invalid format."""
        authorization = "Invalid format"
        api_key = self.auth.extract_api_key(authorization)

        assert api_key is None

    def test_extract_api_key_none(self):
        """Test API key extraction with None input."""
        api_key = self.auth.extract_api_key(None)

        assert api_key is None

    def test_validate_api_key_valid(self):
        """Test API key validation with valid key."""
        valid_key = "sk-test-key-1"
        result = self.auth.validate_api_key(valid_key)

        assert result is True

    def test_validate_api_key_invalid(self):
        """Test API key validation with invalid key."""
        invalid_key = "sk-invalid-key"
        result = self.auth.validate_api_key(invalid_key)

        assert result is False

    def test_get_user_id_from_key(self):
        """Test user ID generation from API key."""
        api_key = "sk-test-key-123"
        user_id = self.auth.get_user_id_from_key(api_key)

        assert isinstance(user_id, str)
        assert len(user_id) == 16  # Should be truncated hash

        # Same key should generate same user ID
        user_id2 = self.auth.get_user_id_from_key(api_key)
        assert user_id == user_id2

    def test_check_rate_limit_within_limits(self):
        """Test rate limiting when within limits."""
        user_id = "test_user_123"
        result = self.auth.check_rate_limit(user_id, requests_per_minute=60, requests_per_hour=1000)

        assert result["allowed"] is True
        assert "remaining_minute" in result
        assert "remaining_hour" in result

    def test_check_rate_limit_minute_exceeded(self):
        """Test rate limiting when minute limit exceeded."""
        user_id = "test_user_123"

        # Make requests up to the limit
        for _ in range(5):
            self.auth.check_rate_limit(user_id, requests_per_minute=5, requests_per_hour=1000)

        # Next request should be rate limited
        result = self.auth.check_rate_limit(user_id, requests_per_minute=5, requests_per_hour=1000)

        assert result["allowed"] is False
        assert "minute" in result["reason"]
        assert "retry_after" in result

    @pytest.mark.asyncio
    async def test_authenticate_request_success(self):
        """Test successful request authentication."""
        mock_request = Mock(spec=Request)
        authorization = "Bearer sk-test-key-1"

        result = await self.auth.authenticate_request(mock_request, authorization)

        assert "user_id" in result
        assert "api_key" in result
        assert "rate_limit" in result
        assert result["api_key"] == "sk-test-key-1"

    @pytest.mark.asyncio
    async def test_authenticate_request_missing_key(self):
        """Test authentication with missing API key."""
        mock_request = Mock(spec=Request)
        authorization = None

        with pytest.raises(HTTPException) as exc_info:
            await self.auth.authenticate_request(mock_request, authorization)

        assert exc_info.value.status_code == 401
        assert "missing_api_key" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_authenticate_request_invalid_key(self):
        """Test authentication with invalid API key."""
        mock_request = Mock(spec=Request)
        authorization = "Bearer sk-invalid-key"

        with pytest.raises(HTTPException) as exc_info:
            await self.auth.authenticate_request(mock_request, authorization)

        assert exc_info.value.status_code == 401
        assert "invalid_api_key" in str(exc_info.value.detail)


class TestRateLimiting:
    """Test rate limiting functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("app.auth.settings") as mock_settings:
            mock_settings.get_allowed_api_keys.return_value = ["sk-test-key"]
            self.auth = APIKeyAuth()

    def test_rate_limit_cleanup(self):
        """Test that old rate limit entries are cleaned up."""
        user_id = "test_user"

        # Add some old entries manually
        current_time = time.time()
        old_minute = int((current_time - 120) // 60)  # 2 minutes ago
        old_hour = int((current_time - 7200) // 3600)  # 2 hours ago

        self.auth.rate_limit_storage[user_id] = {
            "minute_requests": {old_minute: 5},
            "hour_requests": {old_hour: 50},
        }

        # Make a new request - should clean up old entries
        result = self.auth.check_rate_limit(user_id)

        # Old entries should be removed
        assert old_minute not in self.auth.rate_limit_storage[user_id]["minute_requests"]
        assert old_hour not in self.auth.rate_limit_storage[user_id]["hour_requests"]


@pytest.mark.integration
class TestAuthIntegration:
    """Integration tests for authentication system."""

    def test_full_auth_flow(self):
        """Test complete authentication flow."""
        with patch("app.auth.settings") as mock_settings:
            mock_settings.get_allowed_api_keys.return_value = ["sk-integration-test"]
            auth = APIKeyAuth()

            # Test API key extraction
            api_key = auth.extract_api_key("Bearer sk-integration-test")
            assert api_key == "sk-integration-test"

            # Test API key validation
            assert auth.validate_api_key(api_key) is True

            # Test user ID generation
            user_id = auth.get_user_id_from_key(api_key)
            assert isinstance(user_id, str)

            # Test rate limiting
            rate_result = auth.check_rate_limit(user_id)
            assert rate_result["allowed"] is True


if __name__ == "__main__":
    pytest.main([__file__])
