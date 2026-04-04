import re
import sqlite3
from typing import Any

from django.utils import timezone

from apps.channels_config.models import ChannelConfig

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency in some local envs
    psycopg2 = None


IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _is_valid_identifier(value: str) -> bool:
    return bool(value and IDENTIFIER_RE.match(value))


def _qualified_table_name(schema_name: str, table_name: str) -> str:
    if not _is_valid_identifier(table_name):
        raise ValueError('Invalid table name')
    if schema_name:
        if not _is_valid_identifier(schema_name):
            raise ValueError('Invalid schema name')
        return f'"{schema_name}"."{table_name}"'
    return f'"{table_name}"'


def _column_expression(column_name: str) -> str:
    if not _is_valid_identifier(column_name):
        raise ValueError('Invalid column name')
    return f'"{column_name}"'


def build_database_connection_payload(config: ChannelConfig) -> dict[str, Any]:
    credentials = config.credentials or {}
    config_settings = config.settings or {}
    return {
        'id': str(config.id),
        'channel': config.channel,
        'is_active': config.is_active,
        'engine': config_settings.get('engine', 'postgresql'),
        'host': config_settings.get('host', ''),
        'port': config_settings.get('port', 5432),
        'database_name': config_settings.get('database_name', ''),
        'schema_name': config_settings.get('schema_name', 'public'),
        'username': credentials.get('username', ''),
        'password_configured': bool(credentials.get('password')),
        'ssl_mode': config_settings.get('ssl_mode', 'prefer'),
        'connection_status': config_settings.get('connection_status', 'not_configured'),
        'last_tested_at': config_settings.get('last_tested_at'),
        'last_error': config_settings.get('last_error', ''),
        'default_lookup_table': config_settings.get('default_lookup_table', ''),
        'document_column': config_settings.get('document_column', ''),
        'full_name_column': config_settings.get('full_name_column', ''),
        'phone_column': config_settings.get('phone_column', ''),
        'email_column': config_settings.get('email_column', ''),
        'affiliate_type_column': config_settings.get('affiliate_type_column', ''),
        'last_lookup_at': config_settings.get('last_lookup_at'),
        'capabilities': config_settings.get('capabilities', ['affiliate_lookup']),
        'created_at': config.created_at,
        'updated_at': config.updated_at,
    }


def update_database_connection_config(config: ChannelConfig, data: dict[str, Any]) -> ChannelConfig:
    credentials = {**(config.credentials or {})}
    config_settings = {**(config.settings or {})}

    if 'username' in data:
        credentials['username'] = data['username']
    if 'password' in data and data['password']:
        credentials['password'] = data['password']

    for key in [
        'engine',
        'host',
        'port',
        'database_name',
        'schema_name',
        'ssl_mode',
        'default_lookup_table',
        'document_column',
        'full_name_column',
        'phone_column',
        'email_column',
        'affiliate_type_column',
        'capabilities',
    ]:
        if key in data:
            config_settings[key] = data[key]

    if 'is_active' in data:
        config.is_active = data['is_active']

    config.credentials = credentials
    config.settings = config_settings
    config.save()
    return config


def test_database_connection(config: ChannelConfig) -> dict[str, Any]:
    credentials = config.credentials or {}
    config_settings = {**(config.settings or {})}
    engine = config_settings.get('engine', 'postgresql')
    tested_at = timezone.now().isoformat()

    try:
        if engine == 'sqlite':
            database_name = config_settings.get('database_name', '')
            if not database_name:
                raise ValueError('SQLite path is required')
            connection = sqlite3.connect(database_name)
            try:
                cursor = connection.cursor()
                cursor.execute('SELECT 1')
                cursor.fetchone()
            finally:
                connection.close()
        elif engine == 'postgresql':
            if psycopg2 is None:
                raise ValueError('psycopg2 is not installed')
            required = {
                'host': config_settings.get('host', ''),
                'port': config_settings.get('port', 5432),
                'database_name': config_settings.get('database_name', ''),
                'username': credentials.get('username', ''),
                'password': credentials.get('password', ''),
            }
            missing = [key for key, value in required.items() if value in ('', None)]
            if missing:
                raise ValueError(f'Missing required fields: {", ".join(missing)}')
            connection = psycopg2.connect(
                host=required['host'],
                port=required['port'],
                dbname=required['database_name'],
                user=required['username'],
                password=required['password'],
                sslmode=config_settings.get('ssl_mode', 'prefer'),
                connect_timeout=5,
            )
            try:
                cursor = connection.cursor()
                cursor.execute('SELECT 1')
                cursor.fetchone()
            finally:
                connection.close()
        else:
            raise ValueError('Unsupported database engine')
    except Exception as exc:
        config_settings['connection_status'] = 'requires_attention'
        config_settings['last_tested_at'] = tested_at
        config_settings['last_error'] = str(exc)
        config.settings = config_settings
        config.save(update_fields=['settings', 'updated_at'])
        return {
            'status': 'failed',
            'connection_status': config_settings['connection_status'],
            'last_tested_at': tested_at,
            'error': str(exc),
        }

    config_settings['connection_status'] = 'connected'
    config_settings['last_tested_at'] = tested_at
    config_settings['last_error'] = ''
    config.settings = config_settings
    config.save(update_fields=['settings', 'updated_at'])
    return {
        'status': 'connected',
        'connection_status': config_settings['connection_status'],
        'last_tested_at': tested_at,
        'error': '',
    }


def lookup_affiliate_by_document(config: ChannelConfig, document_number: str) -> dict[str, Any]:
    credentials = config.credentials or {}
    config_settings = {**(config.settings or {})}
    engine = config_settings.get('engine', 'postgresql')
    table_name = config_settings.get('default_lookup_table', '')
    document_column = config_settings.get('document_column', '')
    full_name_column = config_settings.get('full_name_column', '')

    if not table_name or not document_column or not full_name_column:
        raise ValueError('Lookup table and required columns are not configured')

    selected_columns = [('full_name', full_name_column)]
    optional_columns = [
        ('phone', config_settings.get('phone_column', '')),
        ('email', config_settings.get('email_column', '')),
        ('affiliate_type', config_settings.get('affiliate_type_column', '')),
    ]
    for alias, column_name in optional_columns:
        if column_name:
            selected_columns.append((alias, column_name))

    qualified_table = _qualified_table_name(config_settings.get('schema_name', ''), table_name)
    selected_sql = ', '.join(
        f'{_column_expression(column_name)} AS "{alias}"'
        for alias, column_name in selected_columns
    )
    where_sql = f'{_column_expression(document_column)} = %s'

    row: tuple[Any, ...] | None = None
    columns = [alias for alias, _ in selected_columns]

    if engine == 'sqlite':
        database_name = config_settings.get('database_name', '')
        if not database_name:
            raise ValueError('SQLite path is required')
        query = (
            f'SELECT {selected_sql.replace("%s", "?")} '
            f'FROM {qualified_table} WHERE {_column_expression(document_column)} = ? LIMIT 1'
        )
        connection = sqlite3.connect(database_name)
        try:
            cursor = connection.cursor()
            cursor.execute(query, [document_number])
            row = cursor.fetchone()
        finally:
            connection.close()
    elif engine == 'postgresql':
        if psycopg2 is None:
            raise ValueError('psycopg2 is not installed')
        query = f'SELECT {selected_sql} FROM {qualified_table} WHERE {where_sql} LIMIT 1'
        connection = psycopg2.connect(
            host=config_settings.get('host', ''),
            port=config_settings.get('port', 5432),
            dbname=config_settings.get('database_name', ''),
            user=credentials.get('username', ''),
            password=credentials.get('password', ''),
            sslmode=config_settings.get('ssl_mode', 'prefer'),
            connect_timeout=5,
        )
        try:
            cursor = connection.cursor()
            cursor.execute(query, [document_number])
            row = cursor.fetchone()
        finally:
            connection.close()
    else:
        raise ValueError('Unsupported database engine')

    config_settings['last_lookup_at'] = timezone.now().isoformat()
    config.settings = config_settings
    config.save(update_fields=['settings', 'updated_at'])

    if row is None:
        return {
            'found': False,
            'record': None,
            'last_lookup_at': config_settings['last_lookup_at'],
        }

    return {
        'found': True,
        'record': dict(zip(columns, row)),
        'last_lookup_at': config_settings['last_lookup_at'],
    }
