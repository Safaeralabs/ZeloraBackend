import secrets
from typing import Any

import httpx
from django.conf import settings
from django.utils import timezone

from apps.channels_config.models import ChannelConfig


def build_embedded_signup_config(config: ChannelConfig, request) -> dict[str, Any]:
    signup = (config.settings or {}).get('embedded_signup', {})
    webhook_url = config.webhook_url or request.build_absolute_uri('/api/channels/whatsapp/webhook/')
    return {
        'enabled': bool(settings.META_APP_ID and settings.META_EMBEDDED_SIGNUP_CONFIG_ID),
        'app_id': settings.META_APP_ID,
        'config_id': settings.META_EMBEDDED_SIGNUP_CONFIG_ID,
        'feature': 'whatsapp_embedded_signup',
        'session_state': signup.get('session_state', ''),
        'session_started_at': signup.get('session_started_at'),
        'session_status': signup.get('session_status', 'idle'),
        'webhook_url': webhook_url,
        'verify_token': settings.WHATSAPP_VERIFY_TOKEN,
    }


def start_embedded_signup(config: ChannelConfig) -> tuple[ChannelConfig, dict[str, Any]]:
    config_settings = {**(config.settings or {})}
    signup_settings = {**config_settings.get('embedded_signup', {})}
    session_state = secrets.token_urlsafe(24)
    signup_settings.update({
        'session_state': session_state,
        'session_started_at': timezone.now().isoformat(),
        'session_status': 'started',
        'last_error': '',
    })
    config_settings['embedded_signup'] = signup_settings
    config_settings['onboarding_status'] = 'embedded_signup_started'
    config.settings = config_settings
    config.save(update_fields=['settings', 'updated_at'])
    return config, signup_settings


def complete_embedded_signup(
    config: ChannelConfig,
    *,
    state: str,
    code: str = '',
    business_portfolio_id: str = '',
    whatsapp_business_account_id: str = '',
    phone_number_id: str = '',
    display_phone_number: str = '',
    verified_name: str = '',
    access_token: str = '',
) -> ChannelConfig:
    config_settings = {**(config.settings or {})}
    signup_settings = {**config_settings.get('embedded_signup', {})}
    expected_state = signup_settings.get('session_state', '')

    if not expected_state or state != expected_state:
        raise ValueError('Invalid embedded signup state')

    credentials = {**(config.credentials or {})}
    exchanged_token = ''
    if code:
        exchanged_token = exchange_code_for_access_token(code)
    final_access_token = access_token or exchanged_token
    if final_access_token:
        credentials['access_token'] = final_access_token
    if phone_number_id:
        credentials['phone_number_id'] = phone_number_id
    if whatsapp_business_account_id:
        credentials['waba_id'] = whatsapp_business_account_id
    if business_portfolio_id:
        credentials['business_portfolio_id'] = business_portfolio_id

    signup_settings.update({
        'session_status': 'completed',
        'completed_at': timezone.now().isoformat(),
        'last_error': '',
    })
    config_settings['embedded_signup'] = signup_settings

    if display_phone_number:
        config_settings['display_phone_number'] = display_phone_number
    if verified_name:
        config_settings['verified_name'] = verified_name
    if phone_number_id:
        config_settings['onboarding_status'] = 'phone_linked'
    if final_access_token and phone_number_id and whatsapp_business_account_id:
        config_settings['onboarding_status'] = 'completed'
    else:
        config_settings['onboarding_status'] = 'meta_authorized'
    config_settings['webhook_status'] = config_settings.get('webhook_status', 'pending')

    config.credentials = credentials
    config.settings = config_settings
    config.is_active = bool(credentials.get('phone_number_id') and credentials.get('access_token'))
    config.save()
    return config


def mark_embedded_signup_failure(config: ChannelConfig, error_message: str) -> ChannelConfig:
    config_settings = {**(config.settings or {})}
    signup_settings = {**config_settings.get('embedded_signup', {})}
    signup_settings.update({
        'session_status': 'failed',
        'last_error': error_message,
        'failed_at': timezone.now().isoformat(),
    })
    config_settings['embedded_signup'] = signup_settings
    config_settings['onboarding_status'] = 'failed'
    config.settings = config_settings
    config.save(update_fields=['settings', 'updated_at'])
    return config


def exchange_code_for_access_token(code: str) -> str:
    if not settings.META_APP_ID or not settings.META_APP_SECRET:
        raise ValueError('Meta app credentials are not configured')

    url = f'{settings.WHATSAPP_BASE_URL}/{settings.WHATSAPP_API_VERSION}/oauth/access_token'
    params = {
        'client_id': settings.META_APP_ID,
        'client_secret': settings.META_APP_SECRET,
        'code': code,
    }
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    return data.get('access_token', '')
