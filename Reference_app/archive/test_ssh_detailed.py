"""
Detailed SSH key diagnostics
"""
import paramiko
import os
import sys

def detailed_test():
    host = "10.20.31.106"
    user = "root"
    ssh_dir = os.path.expanduser("~/.ssh")
    
    print("=" * 60)
    print("SSH Key Diagnostics")
    print("=" * 60)
    
    # Test 1: Check key files
    print("\n1. Checking key files...")
    key_files = [
        ("id_ed25519", paramiko.Ed25519Key),
        ("id_rsa", paramiko.RSAKey),
        ("id_ecdsa", paramiko.ECDSAKey),
    ]
    
    loaded_keys = []
    for key_name, key_class in key_files:
        key_path = os.path.join(ssh_dir, key_name)
        if os.path.exists(key_path):
            print(f"   Found: {key_path}")
            try:
                key = key_class.from_private_key_file(key_path)
                fingerprint = key.get_fingerprint().hex()
                loaded_keys.append((key_name, key, fingerprint))
                print(f"   ✅ Loaded successfully")
                print(f"   Fingerprint: {':'.join([fingerprint[i:i+2] for i in range(0, len(fingerprint), 2)])}")
            except Exception as e:
                print(f"   ❌ Failed to load: {e}")
        else:
            print(f"   Not found: {key_path}")
    
    if not loaded_keys:
        print("\n❌ No SSH keys could be loaded!")
        return False
    
    # Test 2: Check known_hosts
    print("\n2. Checking known_hosts...")
    known_hosts_path = os.path.join(ssh_dir, "known_hosts")
    if os.path.exists(known_hosts_path):
        print(f"   ✅ Found: {known_hosts_path}")
        try:
            with open(known_hosts_path, 'r') as f:
                for line in f:
                    if host in line or "10.20.31.106" in line:
                        print(f"   ✅ Host {host} is in known_hosts")
                        break
        except Exception as e:
            print(f"   ⚠ Cannot read: {e}")
    else:
        print(f"   ⚠ Not found (will be created on first connection)")
    
    # Test 3: Try connection with detailed logging
    print(f"\n3. Testing connection to {user}@{host}...")
    
    # Enable paramiko logging
    paramiko.util.log_to_file('ssh_debug.log')
    
    for key_name, key, fingerprint in loaded_keys:
        print(f"\n   Trying {key_name}...")
        print(f"   Fingerprint: {':'.join([fingerprint[i:i+2] for i in range(0, len(fingerprint), 2)])}")
        
        ssh_client = None
        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Try with pkey
            ssh_client.connect(
                hostname=host,
                username=user,
                pkey=key,
                timeout=10,
                look_for_keys=False,
                allow_agent=False,
                banner_timeout=10
            )
            
            print(f"   ✅ Connection SUCCESS with {key_name}!")
            
            # Test command
            stdin, stdout, stderr = ssh_client.exec_command("hostname")
            hostname = stdout.read().decode().strip()
            print(f"   ✅ Remote hostname: {hostname}")
            
            ssh_client.close()
            
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS! Working key: {key_name}")
            print(f"{'='*60}")
            return True
            
        except paramiko.AuthenticationException as e:
            print(f"   ❌ Authentication failed: {e}")
            print(f"      Check: ssh_debug.log for details")
            
        except paramiko.SSHException as e:
            print(f"   ❌ SSH error: {e}")
            
        except Exception as e:
            print(f"   ❌ Error: {type(e).__name__}: {e}")
            
        finally:
            if ssh_client:
                try:
                    ssh_client.close()
                except:
                    pass
    
    print(f"\n{'='*60}")
    print("❌ All keys failed!")
    print("Check ssh_debug.log for detailed information")
    print(f"{'='*60}")
    
    # Test 4: Compare with OpenSSH
    print("\n4. Testing with system SSH command...")
    import subprocess
    try:
        result = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 
             f'{user}@{host}', 'hostname'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print(f"   ✅ System SSH works! Remote hostname: {result.stdout.strip()}")
            print(f"   ⚠ But Paramiko failed - there may be a compatibility issue")
        else:
            print(f"   ❌ System SSH also fails: {result.stderr}")
    except Exception as e:
        print(f"   ⚠ Cannot test system SSH: {e}")
    
    return False

if __name__ == "__main__":
    success = detailed_test()
    sys.exit(0 if success else 1)
