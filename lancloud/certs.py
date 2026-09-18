# -*- coding: utf-8 -*-
"""自签名 HTTPS 证书管理

生成一个本地 CA + 服务器证书（SAN 覆盖全部局域网 IP 与已配置的域名映射）。
- CA 证书可下载并在设备上安装为"受信任的根证书"，安装后 HTTPS 无警告；
- 未安装时浏览器会提示"证书不受信任"，点"高级 → 继续访问"仍可查看内容。
"""
import datetime
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from . import config

CERT_DIR = config.DATA_DIR / "certs"
CA_KEY = CERT_DIR / "ca.key"
CA_CRT = CERT_DIR / "ca.crt"
SRV_KEY = CERT_DIR / "server.key"
SRV_CRT = CERT_DIR / "server.crt"
VALID_DAYS = 3650  # 10 年


def _generate_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LanCloud Local CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                           critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True,
                                         key_cert_sign=True, key_encipherment=True,
                                         content_commitment=False, data_encipherment=False,
                                         crl_sign=True, encipher_only=False,
                                         decipher_only=False, key_agreement=False),
                           critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                           critical=False)
            .sign(key, hashes.SHA256()))
    CA_KEY.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    CA_CRT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _generate_server_cert(hosts: list, ips: list):
    ca_key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
    ca_crt = x509.load_pem_x509_certificate(CA_CRT.read_bytes())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LanCloud Server")])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = [x509.DNSName("localhost")]
    for h in hosts:
        h = h.strip().lower().rstrip(".")
        if h:
            san.append(x509.DNSName(h))
    seen_ips = set()
    for ip in ips:
        ip = ip.strip()
        if not ip or ip in seen_ips:
            continue
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
            seen_ips.add(ip)
        except ValueError:
            pass
    cert = (x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(ca_crt.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                           critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True,
                                         key_cert_sign=False, key_encipherment=True,
                                         content_commitment=False, data_encipherment=False,
                                         crl_sign=False, encipher_only=False,
                                         decipher_only=False, key_agreement=False),
                           critical=True)
            .sign(ca_key, hashes.SHA256()))
    SRV_KEY.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    SRV_CRT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _cert_san_hosts() -> set:
    """读取现有服务器证书中的 SAN 域名，用于判断是否需要重签"""
    try:
        cert = x509.load_pem_x509_certificate(SRV_CRT.read_bytes())
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        return {s.value for s in ext.value}
    except Exception:
        return set()


def ensure_certs(hosts: list, ips: list) -> dict:
    """确保 CA 与服务器证书存在且 SAN 覆盖当前域名/IP；返回证书信息"""
    config.ensure_dirs()
    if not (CA_KEY.exists() and CA_CRT.exists()):
        _generate_ca()
    hosts = list(dict.fromkeys([h for h in hosts if h]))
    ips = list(dict.fromkeys([i for i in ips if i]))
    need = {("DNS", h) for h in hosts} | {("IP", i) for i in ips}
    try:
        cert = x509.load_pem_x509_certificate(SRV_CRT.read_bytes())
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        have = {("DNS", s.value) for s in ext.value if isinstance(s, x509.DNSName)} | \
               {("IP", str(s.value)) for s in ext.value if isinstance(s, x509.IPAddress)}
    except Exception:
        have = set()
    if not (SRV_KEY.exists() and SRV_CRT.exists()) or not need.issubset(have):
        _generate_server_cert(hosts, ips)
    return {"ca": str(CA_CRT), "cert": str(SRV_CRT), "key": str(SRV_KEY)}
