"""migrate_github_repo_name_from_auth_to_config

Revision ID: 6e39730bc45b
Revises: c60291fb2129
Create Date: 2025-09-28 22:12:53.758477

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import json
import os
import sys

# Add the backend directory to the Python path to import our modules
backend_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, backend_dir)

try:
    from airweave.core.credentials import decrypt, encrypt
    CREDENTIALS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import credentials module: {e}")
    print("Migration will skip actual credential processing")
    CREDENTIALS_AVAILABLE = False


# revision identifiers, used by Alembic.
revision = '6e39730bc45b'
down_revision = 'c60291fb2129'
branch_labels = None
depends_on = None


def upgrade():
    """Migrate GitHub repo_name from encrypted credentials to config_fields.
    
    This migration:
    1. Finds GitHub source connections missing repo_name in config_fields
    2. Decrypts their integration credentials
    3. Extracts repo_name from GitHubAuthConfig (if it exists in old credentials)
    4. Adds repo_name to source_connection.config_fields
    5. Removes repo_name from encrypted credentials
    6. Re-encrypts and saves credentials
    """
    
    # Get database connection
    conn = op.get_bind()
    
    # Find GitHub connections that need migration
    result = conn.execute(text("""
        SELECT 
            sc.id as source_connection_id,
            sc.name,
            sc.config_fields,
            ic.id as credential_id,
            ic.encrypted_credentials
        FROM source_connection sc
        JOIN connection c ON sc.connection_id = c.id
        JOIN integration_credential ic ON c.integration_credential_id = ic.id
        WHERE sc.short_name = 'github'
        AND (sc.config_fields IS NULL OR sc.config_fields::text NOT LIKE '%repo_name%')
    """))
    
    connections_to_migrate = result.fetchall()
    
    print(f"Found {len(connections_to_migrate)} GitHub connections to migrate")
    
    for row in connections_to_migrate:
        source_connection_id = row.source_connection_id
        name = row.name
        config_fields = row.config_fields or {}
        credential_id = row.credential_id
        encrypted_credentials = row.encrypted_credentials
        
        print(f"Migrating connection: {name} (ID: {source_connection_id})")
        
        try:
            if CREDENTIALS_AVAILABLE:
                # Decrypt the actual credentials
                decrypted_credentials = decrypt(encrypted_credentials)
                print(f"  Decrypted credentials keys: {list(decrypted_credentials.keys())}")
                
                # Check if repo_name exists in the old credentials
                if 'repo_name' in decrypted_credentials:
                    repo_name = decrypted_credentials['repo_name']
                    print(f"  Found repo_name in credentials: {repo_name}")
                    
                    # Add repo_name to config_fields
                    config_fields['repo_name'] = repo_name
                    
                    # Remove repo_name from credentials
                    del decrypted_credentials['repo_name']
                    
                    # Re-encrypt credentials without repo_name
                    new_encrypted_credentials = encrypt(decrypted_credentials)
                    
                    # Update both source_connection and integration_credential
                    conn.execute(text("""
                        UPDATE source_connection 
                        SET config_fields = :config_fields
                        WHERE id = :source_connection_id
                    """), {
                        'config_fields': json.dumps(config_fields),
                        'source_connection_id': source_connection_id
                    })
                    
                    conn.execute(text("""
                        UPDATE integration_credential 
                        SET encrypted_credentials = :encrypted_credentials
                        WHERE id = :credential_id
                    """), {
                        'encrypted_credentials': new_encrypted_credentials,
                        'credential_id': credential_id
                    })
                    
                    print(f"  ✅ Migrated repo_name '{repo_name}' to config_fields for {name}")
                    
                else:
                    # No repo_name in old credentials, add a placeholder
                    config_fields['repo_name'] = 'migration-placeholder/repo'
                    
                    conn.execute(text("""
                        UPDATE source_connection 
                        SET config_fields = :config_fields
                        WHERE id = :source_connection_id
                    """), {
                        'config_fields': json.dumps(config_fields),
                        'source_connection_id': source_connection_id
                    })
                    
                    print(f"  ⚠️  No repo_name in credentials, added placeholder for {name}")
            else:
                # Fallback: Add placeholder repo_name when credentials module unavailable
                config_fields['repo_name'] = 'migration-placeholder/repo'
                
                conn.execute(text("""
                    UPDATE source_connection 
                    SET config_fields = :config_fields
                    WHERE id = :source_connection_id
                """), {
                    'config_fields': json.dumps(config_fields),
                    'source_connection_id': source_connection_id
                })
                
                print(f"  ⚠️  Credentials module unavailable, added placeholder for {name}")
                
        except Exception as e:
            print(f"  ❌ Failed to migrate {name}: {e}")
            # Continue with other connections


def downgrade():
    """Reverse the migration by moving repo_name back to encrypted credentials.
    
    Note: This is complex because we'd need to:
    1. Extract repo_name from config_fields
    2. Decrypt existing credentials
    3. Add repo_name to GitHubAuthConfig
    4. Re-encrypt credentials
    5. Remove repo_name from config_fields
    
    For safety, we'll just log a warning.
    """
    print("Downgrade not implemented - manual intervention required")
    print("To reverse this migration:")
    print("1. Extract repo_name from config_fields")
    print("2. Add repo_name to encrypted credentials")
    print("3. Remove repo_name from config_fields")