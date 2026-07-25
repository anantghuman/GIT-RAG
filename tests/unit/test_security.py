import hashlib
import hmac

from gitrag.api.security import verify_github_signature


def test_github_signature_verification():
    secret = "top-secret"
    body = b'{"ref":"refs/heads/main"}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_github_signature(secret, body, signature)
    assert not verify_github_signature(secret, body, "sha256=bad")
    assert not verify_github_signature(secret, body, None)
    assert verify_github_signature("", body, None)
