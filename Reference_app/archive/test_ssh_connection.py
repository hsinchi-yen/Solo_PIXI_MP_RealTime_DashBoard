"""
Quick SSH connection test with paramiko
"""
import paramiko
import os

def test_ssh():
    host = "10.20.31.106"
    user = "root"
    
    # Find all keys
    ssh_dir = os.path.expanduser("~/.ssh")
    key_candidates = [
        ("id_ed25519", paramiko.Ed25519Key),
        ("id_ecdsa", paramiko.ECDSAKey),
        ("id_rsa", paramiko.RSAKey),
    ]
    
    loaded_keys = []
    
    print("Loading SSH keys...")
    for key_name, key_class in key_candidates:
        key_path = os.path.join(ssh_dir, key_name)
        if os.path.exists(key_path):
            try:
                key = key_class.from_private_key_file(key_path)
                loaded_keys.append((key_name, key))
                print(f"✅ Loaded {key_name} as {key_class.__name__}")
            except Exception as e:
                print(f"❌ Failed to load {key_name}: {e}")
    
    if not loaded_keys:
        print("❌ No SSH keys found!")
        return False
    
    print(f"\nAttempting to connect to {user}@{host}...")
    
    # Try each key individually
    for key_name, key in loaded_keys:
        ssh_client = None
        try:
            print(f"\nTrying with {key_name}...")
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect with specific key object (pkey)
            ssh_client.connect(
                hostname=host,
                username=user,
                pkey=key,  # Use loaded key object directly
                timeout=10,
                look_for_keys=False,  # Don't look for additional keys
                allow_agent=False     # Don't use agent
            )
            
            print(f"✅ SSH connection successful with {key_name}!")
            
            # Test SFTP
            sftp = ssh_client.open_sftp()
            print("✅ SFTP working!")
            sftp.close()
            
            # Test command execution
            stdin, stdout, stderr = ssh_client.exec_command("hostname")
            hostname = stdout.read().decode().strip()
            print(f"✅ Remote hostname: {hostname}")
            
            ssh_client.close()
            return True
            
        except paramiko.AuthenticationException as e:
            print(f"❌ Authentication failed with {key_name}: {e}")
            
        except Exception as e:
            print(f"❌ Connection failed with {key_name}: {type(e).__name__}: {e}")
            
        finally:
            if ssh_client:
                try:
                    ssh_client.close()
                except:
                    pass
    
    print("\n❌ All keys failed!")
    return False

if __name__ == "__main__":
    success = test_ssh()
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Tests failed! Server may not have your public key.")
