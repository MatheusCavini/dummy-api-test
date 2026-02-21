VALID_KEYS = ["sk_test_123"]

def validate_api_key(auth_header):
    if not auth_header:
        return False
    
    key = auth_header.replace("Bearer ", "")
    return key in VALID_KEYS
