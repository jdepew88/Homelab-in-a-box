import bcrypt
import getpass

password = getpass.getpass("New password: ").encode()
confirm = getpass.getpass("Confirm password: ").encode()
if password != confirm:
    raise SystemExit("Passwords do not match.")
hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12)).decode()
print(hashed)
