# smb_test.py
from smb.SMBConnection import SMBConnection

# ================= CONFIGURATION =================
username = 'gestion'       # ton login SMB
password = 'Aeronav99'      # ton mot de passe SMB
client_name = 'admin'           # nom de ton PC (n'importe quoi)
server_name = 'NAS_SERVER'          # nom NetBIOS du NAS (ou IP)
server_ip = '10.61.17.33'         # IP du NAS
shared_folder = 'NAS'           # nom du dossier partagé SMB
domain_name = ''                     # laisse vide si pas de domaine

# ================== CONNEXION ==================
conn = SMBConnection(username, password, client_name, server_name, domain=domain_name, use_ntlm_v2=True, is_direct_tcp=True)
# assert conn.connect(server_ip, 139), "Connexion échouée !"  # port 139 ou 445 selon le NAS

if conn.connect(server_ip, 445):
    print("Connexion réussie !")

    # Lister les fichiers du partage
    files = conn.listPath(shared_folder, '/')
    for f in files:
        print(f.filename, "<DIR>" if f.isDirectory else f.file_size)
else:
    print("Connexion échouée !")
