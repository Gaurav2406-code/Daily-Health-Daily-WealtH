import hashlib
import hmac
import secrets
import re

def hash_password(password: str) -> str:
    """
    PBKDF2-HMAC-SHA256 के साथ सुरक्षित साल्टेड पासवर्ड हैश जनरेट करता है।
    फॉर्मेट: pbkdf2_sha256$<iterations>$<salt>$<hash>
    """
    salt = secrets.token_hex(16)
    iterations = 100000
    derived = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${derived.hex()}"

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    पासवर्ड को टाइमिंग-सेफ तरीके से वेरिफाई करता है।
    पुराने लीगेसी SHA-256 हैश के साथ भी बैकवर्ड-कम्पैटिबल है।
    """
    if not stored_hash:
        return False

    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            parts = stored_hash.split("$")
            if len(parts) != 4:
                return False
            _, iters_s, salt, hash_hex = parts
            iterations = int(iters_s)
            derived = hashlib.pbkdf2_hmac(
                'sha256',
                plain_password.encode('utf-8'),
                salt.encode('utf-8'),
                iterations
            )
            return hmac.compare_digest(derived.hex(), hash_hex)
        except Exception:
            return False
    else:
        # बैकवर्ड कम्पैटिबिलिटी (लीगेसी SHA256)
        legacy_hash = hashlib.sha256(plain_password.strip().encode()).hexdigest()
        return hmac.compare_digest(legacy_hash, stored_hash)

def validate_password_strength(pw: str) -> tuple[bool, str]:
    """पासवर्ड की मजबूती की जांच करता है"""
    if len(pw) < 8:
        return False, "पासवर्ड में कम से कम 8 अक्षर होने चाहिए।"
    if not re.search(r"[A-Z]", pw):
        return False, "पासवर्ड में कम से कम 1 बड़ा अक्षर (A-Z) होना चाहिए।"
    if not re.search(r"[a-z]", pw):
        return False, "पासवर्ड में कम से कम 1 छोटा अक्षर (a-z) होना चाहिए।"
    if not re.search(r"[0-9]", pw):
        return False, "पासवर्ड में कम से कम 1 संख्या (0-9) होनी चाहिए।"
    if not re.search(r"[@$!%*?&#^_\-]", pw):
        return False, "पासवर्ड में कम से कम 1 स्पेशल कैरेक्टर (@, $, !, %, *, ?, &, # आदि) होना चाहिए।"
    return True, ""
