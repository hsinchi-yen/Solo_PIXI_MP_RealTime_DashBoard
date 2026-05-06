"""
Test SSH connection with "none" authentication method
"""
import paramiko

def test_none_auth():
    host = "10.20.31.106"
    user = "root"
    
    print(f"Testing connection to {user}@{host} with 'none' authentication...")
    
    ssh_client = None
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Method 1: Simply connect without any authentication
        print("\nMethod 1: Connect with password='' and no keys...")
        ssh_client.connect(
            hostname=host,
            username=user,
            password='',  # Empty password to try none auth
            timeout=10,
            look_for_keys=False,  # Don't try keys
            allow_agent=False     # Don't use agent
        )
        
        print("✅ Connected successfully!")
        
        # Test SFTP
        sftp = ssh_client.open_sftp()
        print("✅ SFTP working!")
        sftp.close()
        
        # Test command
        stdin, stdout, stderr = ssh_client.exec_command("hostname")
        hostname = stdout.read().decode().strip()
        print(f"✅ Remote hostname: {hostname}")
        
        ssh_client.close()
        return True
        
    except paramiko.AuthenticationException as e:
        print(f"❌ Authentication failed: {e}")
        
        # Method 2: Use Transport directly to try none auth
        print("\nMethod 2: Using Transport API for none auth...")
        try:
            transport = paramiko.Transport((host, 22))
            transport.connect(username=user)
            
            # Try none authentication
            transport.auth_none(user)
            
            if transport.is_authenticated():
                print("✅ 'none' authentication successful!")
                
                # Open SFTP
                sftp = paramiko.SFTPClient.from_transport(transport)
                print("✅ SFTP working!")
                sftp.close()
                
                # Run command
                session = transport.open_session()
                session.exec_command("hostname")
                hostname = session.recv(1024).decode().strip()
                print(f"✅ Remote hostname: {hostname}")
                session.close()
                
                transport.close()
                return True
            else:
                print("❌ 'none' auth did not work")
                transport.close()
                
        except Exception as e2:
            print(f"❌ Transport method failed: {e2}")
        
        return False
        
    except Exception as e:
        print(f"❌ Connection failed: {type(e).__name__}: {e}")
        return False
        
    finally:
        if ssh_client:
            try:
                ssh_client.close()
            except:
                pass

if __name__ == "__main__":
    success = test_none_auth()
    if success:
        print("\n✅ SUCCESS! Found working authentication method.")
    else:
        print("\n❌ All methods failed.")
