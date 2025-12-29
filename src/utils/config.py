"""
Configuration and secrets management for the Provider Recommender app.

This module provides a centralized way to access application configuration
and secrets, with proper fallbacks and validation. It demonstrates best
practices for handling secrets in Streamlit applications.

Usage:
    from src.utils.config import get_api_config, get_database_config

    # Get geocoding API configuration
    geocoding_config = get_api_config('geocoding')
    google_api_key = geocoding_config.get('google_maps_api_key')

    # Get database configuration
    db_config = get_database_config()
    database_url = db_config.get('url')
"""

import logging
from typing import Any, Dict

import streamlit as st

logger = logging.getLogger(__name__)


def get_secret(key_path: str, default: Any = None) -> Any:
    """
    Safely retrieve a secret from Streamlit's secrets management.

    Args:
        key_path: Dot-notation path to the secret (e.g., 'database.url')
        default: Default value if secret is not found

    Returns:
        The secret value or default if not found

    Examples:
        >>> get_secret('database.url', '')
        >>> get_secret('geocoding.google_maps_api_key')
        >>> get_secret('app.debug_mode', False)
    """
    try:
        # Split the key path to navigate nested mappings
        keys = key_path.split(".")
        value = st.secrets

        for key in keys:
            try:
                # Try mapping-style access (works for dict-like and Streamlit secrets)
                value = value[key]
            except Exception:
                # If any access fails, return the provided default
                return default

        return value
    except Exception as e:
        logger.warning(f"Failed to retrieve secret '{key_path}': {e}")
        return default


def get_api_config(api_name: str) -> Dict[str, Any]:
    """
    Get configuration for a specific API or service.

    Args:
        api_name: Name of the API/service (e.g., 'geocoding', 'database')

    Returns:
        Dictionary containing the API configuration
    """
    if api_name == "geocoding":
        return {
            "google_maps_api_key": get_secret("geocoding.google_maps_api_key", ""),
            "google_maps_enabled": get_secret("geocoding.google_maps_enabled", False),
            "nominatim_user_agent": get_secret("geocoding.nominatim_user_agent", "jlg_provider_recommender"),
            "request_timeout": get_secret("geocoding.request_timeout", 10),
            "rate_limit_delay": get_secret("geocoding.rate_limit_delay", 1.0),
            "max_retries": get_secret("geocoding.max_retries", 3),
        }
    elif api_name == "filevine":
        return {
            "api_key": get_secret("apis.filevine_api_key", ""),
            "base_url": get_secret("apis.filevine_base_url", "https://api.filevine.com"),
            "org_id": get_secret("apis.filevine_org_id", ""),
        }
    elif api_name == "email":
        return {
            "smtp_server": get_secret("apis.smtp_server", ""),
            "smtp_port": get_secret("apis.smtp_port", 587),
            "smtp_username": get_secret("apis.smtp_username", ""),
            "smtp_password": get_secret("apis.smtp_password", ""),
            "from_email": get_secret("apis.from_email", ""),
        }
    elif api_name == "s3":
        return {
            "aws_access_key_id": get_secret("s3.aws_access_key_id", ""),
            "aws_secret_access_key": get_secret("s3.aws_secret_access_key", ""),
            "bucket_name": get_secret("s3.bucket_name", ""),
            "region_name": get_secret("s3.region_name", "us-east-1"),
            "referrals_folder": get_secret("s3.referrals_folder", "referrals"),
            "preferred_providers_folder": get_secret("s3.preferred_providers_folder", "preferred_providers"),
            "use_latest_file": get_secret("s3.use_latest_file", True),
        }
    else:
        return {}


def get_database_config() -> Dict[str, Any]:
    """
    Get database connection configuration.

    Returns:
        Dictionary containing database configuration
    """
    return {
        "url": get_secret("database.url", ""),
        "username": get_secret("database.username", ""),
        "password": get_secret("database.password", ""),
        "host": get_secret("database.host", ""),
        "port": get_secret("database.port", 5432),
        "database_name": get_secret("database.database_name", ""),
        "ssl_mode": get_secret("database.ssl_mode", "require"),
    }


def get_app_config() -> Dict[str, Any]:
    """
    Get general application configuration.

    Returns:
        Dictionary containing app configuration
    """
    return {
        "environment": get_secret("app.environment", "production"),
        "debug_mode": get_secret("app.debug_mode", False),
        "log_level": get_secret("app.log_level", "INFO"),
    }


def get_security_config() -> Dict[str, Any]:
    """
    Get security and rate limiting configuration.

    Returns:
        Dictionary containing security configuration
    """
    return {
        "allowed_hosts": get_secret("security.allowed_hosts", ["*.streamlit.app", "localhost"]),
        "max_requests_per_hour": get_secret("security.max_requests_per_hour", 1000),
        "max_geocoding_requests_per_day": get_secret("security.max_geocoding_requests_per_day", 2500),
        "session_timeout_minutes": get_secret("security.session_timeout_minutes", 60),
        "api_key_header": get_secret("security.api_key_header", "X-API-Key"),
    }


def get_cache_config() -> Dict[str, Any]:
    """
    Get caching configuration.

    Returns:
        Dictionary containing cache configuration
    """
    return {
        "ttl_hours": get_secret("cache.ttl_hours", 24),
        "max_size_mb": get_secret("cache.max_size_mb", 100),
        "redis_url": get_secret("cache.redis_url", ""),
        "enable_redis": get_secret("cache.enable_redis", False),
    }


def is_api_enabled(api_name: str) -> bool:
    """
    Check if a specific API is enabled and properly configured.

    Args:
        api_name: Name of the API to check

    Returns:
        True if the API is enabled and has required configuration
    """
    if api_name == "google_maps":
        config = get_api_config("geocoding")
        return config["google_maps_enabled"] and bool(config["google_maps_api_key"])
    elif api_name == "filevine":
        config = get_api_config("filevine")
        return bool(config["api_key"]) and bool(config["org_id"])
    elif api_name == "database":
        config = get_database_config()
        return bool(config["url"]) or (bool(config["host"]) and bool(config["database_name"]))
    elif api_name == "email":
        config = get_api_config("email")
        return bool(config["smtp_server"]) and bool(config["smtp_username"])
    elif api_name == "s3":
        config = get_api_config("s3")
        return (
            bool(config["aws_access_key_id"]) and bool(config["aws_secret_access_key"]) and bool(config["bucket_name"])
        )
    else:
        return False


def validate_configuration() -> Dict[str, str]:
    """
    Validate the application configuration and return any warnings or errors.

    Returns:
        Dictionary with configuration validation results
    """
    issues = {}

    # Check geocoding configuration
    geocoding_config = get_api_config("geocoding")
    if geocoding_config["google_maps_enabled"] and not geocoding_config["google_maps_api_key"]:
        issues["geocoding"] = "Google Maps is enabled but no API key is provided"

    # Check database configuration
    db_config = get_database_config()
    if db_config["url"]:
        # If URL is provided, it should be valid
        if not db_config["url"].startswith(("postgresql://", "mysql://", "sqlite:///")):
            issues["database"] = "Database URL format may be invalid"
    elif db_config["host"]:
        # If host is provided, check for required fields
        if not db_config["database_name"]:
            issues["database"] = "Database host provided but database name is missing"

    # Check app environment
    app_config = get_app_config()
    if app_config["environment"] not in ["development", "staging", "production"]:
        issues["app"] = f"Unknown environment: {app_config['environment']}"

    return issues


# Convenience function for backwards compatibility
def get_legacy_credentials() -> Dict[str, str]:
    """
    Get legacy API credentials for backwards compatibility.

    Returns:
        Dictionary containing legacy credentials
    """
    return {
        "lead_docket_api_key": get_secret("lead_docket_api_key", ""),
        "lead_docket_base_api_endpoint": get_secret("lead_docket_base_api_endpoint", ""),
    }


if __name__ == "__main__":
    # Example usage and testing
    print("Provider Recommender - Configuration Status")
    print("=" * 50)

    # Validate configuration
    issues = validate_configuration()
    if issues:
        print("⚠️  Configuration Issues Found:")
        for component, issue in issues.items():
            print(f"  - {component}: {issue}")
    else:
        print("✅ Configuration validation passed")

    print("\n📋 API Status:")
    apis = ["google_maps", "filevine", "database", "email"]
    for api in apis:
        status = "✅ Enabled" if is_api_enabled(api) else "❌ Disabled/Not configured"
        print(f"  - {api}: {status}")

    print(f"\n🔧 Environment: {get_app_config()['environment']}")
    print(f"🐛 Debug Mode: {get_app_config()['debug_mode']}")
