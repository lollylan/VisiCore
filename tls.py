"""
VisiCore - TLS-Zertifikat-Verwaltung
Generiert beim ersten Start ein selbst-signiertes Zertifikat
fuer verschluesselte HTTPS-Verbindungen im Praxisnetzwerk.
"""

import os
import socket
import datetime

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _get_lan_ips():
    """Ermittelt alle lokalen IP-Adressen dieses Rechners."""
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.'):
                ips.add(ip)
    except socket.gaierror:
        pass

    # Fallback: UDP-Socket-Trick
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        if not ip.startswith('127.'):
            ips.add(ip)
        s.close()
    except OSError:
        pass

    return list(ips)


def ensure_certificate(data_dir):
    """
    Stellt sicher, dass ein TLS-Zertifikat existiert.
    Generiert bei Bedarf ein neues selbst-signiertes Zertifikat.

    Returns:
        tuple: (cert_path, key_path)
    """
    cert_path = os.path.join(data_dir, 'visicore.crt')
    key_path = os.path.join(data_dir, 'visicore.key')

    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    os.makedirs(data_dir, exist_ok=True)

    # RSA-Schluessel generieren
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Subject / Issuer
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'DE'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Arztpraxis'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'VisiCore'),
    ])

    # Subject Alternative Names: localhost + alle LAN-IPs
    san_entries = [
        x509.DNSName('localhost'),
        x509.IPAddress(ipaddress_from_string('127.0.0.1')),
    ]
    for ip in _get_lan_ips():
        san_entries.append(x509.IPAddress(ipaddress_from_string(ip)))

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 Jahre
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Schluessel speichern
    with open(key_path, 'wb') as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Zertifikat speichern
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    lan_ips = _get_lan_ips()
    ip_info = ', '.join(lan_ips) if lan_ips else 'keine erkannt'
    print(f'  TLS-Zertifikat erstellt (IPs: {ip_info})')
    print()
    print('  HINWEIS: Beim ersten Zugriff zeigt der Browser eine')
    print('  Sicherheitswarnung. Klicken Sie auf "Erweitert" und')
    print('  dann auf "Weiter zu ...". Dies ist normal bei')
    print('  selbst-signierten Zertifikaten im lokalen Netzwerk.')
    print()

    return cert_path, key_path


def ipaddress_from_string(ip_str):
    """Konvertiert einen IP-String in ein ipaddress-Objekt."""
    import ipaddress
    return ipaddress.ip_address(ip_str)
