from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.open import Open, CreateOptions, FileAttributes
from smbprotocol.file_info import FileDirectoryInformation

import uuid

# ================= CONFIGURATION =================
username = "gestion"
password = "Aeronav99"
server_ip = "10.61.17.33"
server_name = "SERVER"
shared_folder = "NAS"
client_name = "admin"
server_port = 445

# ================== CONNEXION ==================
conn = Connection(uuid.uuid4(), server_ip, server_port)
conn.connect()

session = Session(conn, username, password)
session.connect()

tree = TreeConnect(session, r"\\{}\{}".format(server_ip, shared_folder))
tree.connect()

# ================== LISTER LE CONTENU ==================
root_open = Open(tree, "/")
root_open.create(
    impersonation_level=None,       # pas obligatoire si SMB2/3
    desired_access=FileAttributes.FILE_READ_ATTRIBUTES,  # lecture de l’attribut
    file_attributes=FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
    share_access=0,
    create_disposition=1,           # FILE_OPEN
    create_options=CreateOptions.FILE_DIRECTORY_FILE
)

for f in root_open.query_directory("*", file_information_class=FileDirectoryInformation):
    name = f['FileName'].get_value()
    is_dir = f['FileAttributes'].get_value() & FileAttributes.FILE_ATTRIBUTE_DIRECTORY
    print(name, "<DIR>" if is_dir else "FILE")
