"""
Local mock documentation server for testing the full Web2PDF pipeline.
Simulates a multi-page documentation site with internal and external links.
"""

import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import sys

PAGES = {
    "/docs/": """<!DOCTYPE html>
<html><head><title>Anyware Manager - Home</title></head>
<body>
<nav class="sidebar">
  <a href="/docs/">Home</a>
  <a href="/docs/installation/">Installation Guide</a>
  <a href="/docs/configuration/">Configuration</a>
  <a href="/docs/troubleshooting/">Troubleshooting</a>
</nav>
<main>
  <h1>Anyware Manager Enterprise Documentation</h1>
  <p>Welcome to the Anyware Manager Enterprise documentation. This guide covers installation, configuration, and management of your Anyware deployment.</p>

  <h2>Getting Started</h2>
  <p>To get started, follow the <a href="/docs/installation/">Installation Guide</a> to set up your environment.</p>
  <p>Once installed, proceed to <a href="/docs/configuration/">Configuration</a> to customize your deployment.</p>

  <h2>External Resources</h2>
  <ul>
    <li><a href="https://github.com/anyware/manager">GitHub Repository</a> - Source code and issue tracker</li>
    <li><a href="https://support.hp.com">HP Support</a> - Official support portal</li>
    <li><a href="https://community.hp.com/anyware">Community Forum</a> - Ask questions and share knowledge</li>
  </ul>

  <h2>System Requirements</h2>
  <table>
    <tr><th>Component</th><th>Minimum</th><th>Recommended</th></tr>
    <tr><td>CPU</td><td>4 cores</td><td>8 cores</td></tr>
    <tr><td>RAM</td><td>8 GB</td><td>16 GB</td></tr>
    <tr><td>Storage</td><td>50 GB SSD</td><td>100 GB SSD</td></tr>
    <tr><td>OS</td><td>Ubuntu 20.04</td><td>Ubuntu 22.04</td></tr>
  </table>

  <p>If you run into issues, check the <a href="/docs/troubleshooting/">Troubleshooting</a> page.</p>
</main>
</body></html>""",

    "/docs/installation/": """<!DOCTYPE html>
<html><head><title>Installation Guide - Anyware Manager</title></head>
<body>
<nav class="sidebar">
  <a href="/docs/">Home</a>
  <a href="/docs/installation/">Installation Guide</a>
  <a href="/docs/configuration/">Configuration</a>
  <a href="/docs/troubleshooting/">Troubleshooting</a>
</nav>
<main>
  <h1>Installation Guide</h1>
  <p>This page describes how to install Anyware Manager Enterprise on your infrastructure.</p>

  <h2>Prerequisites</h2>
  <ul>
    <li>A supported Linux distribution (see <a href="/docs/">System Requirements</a>)</li>
    <li>Root or sudo access</li>
    <li>Network connectivity to the license server</li>
    <li>Docker 20.10+ (see <a href="https://docs.docker.com/engine/install/">Docker installation docs</a>)</li>
  </ul>

  <h2>Step 1: Download the Installer</h2>
  <pre><code>curl -fsSL https://get.anyware.hp.com/install.sh -o install.sh
chmod +x install.sh</code></pre>

  <h2>Step 2: Run the Installer</h2>
  <pre><code>sudo ./install.sh --accept-license \\
  --admin-email admin@example.com \\
  --domain manager.example.com</code></pre>

  <h2>Step 3: Verify Installation</h2>
  <p>After installation, verify that all services are running:</p>
  <pre><code>sudo systemctl status anyware-manager
sudo anyware-manager health-check</code></pre>

  <blockquote>
    <strong>Note:</strong> If the health check fails, see the <a href="/docs/troubleshooting/">Troubleshooting</a> page for common solutions.
  </blockquote>

  <p>Once installation is verified, proceed to <a href="/docs/configuration/">Configuration</a>.</p>
</main>
</body></html>""",

    "/docs/configuration/": """<!DOCTYPE html>
<html><head><title>Configuration - Anyware Manager</title></head>
<body>
<nav class="sidebar">
  <a href="/docs/">Home</a>
  <a href="/docs/installation/">Installation Guide</a>
  <a href="/docs/configuration/">Configuration</a>
  <a href="/docs/troubleshooting/">Troubleshooting</a>
</nav>
<main>
  <h1>Configuration</h1>
  <p>After <a href="/docs/installation/">installing Anyware Manager</a>, configure it for your environment.</p>

  <h2>Configuration File</h2>
  <p>The main configuration file is located at <code>/etc/anyware-manager/config.yaml</code>:</p>
  <pre><code>server:
  host: 0.0.0.0
  port: 443
  tls:
    cert: /etc/ssl/certs/server.crt
    key: /etc/ssl/private/server.key

database:
  host: localhost
  port: 5432
  name: anyware_manager
  user: anyware
  password: ${DB_PASSWORD}

logging:
  level: info
  file: /var/log/anyware-manager/app.log</code></pre>

  <h2>Authentication</h2>
  <p>Anyware Manager supports multiple authentication backends:</p>
  <table>
    <tr><th>Provider</th><th>Protocol</th><th>Documentation</th></tr>
    <tr><td>Active Directory</td><td>LDAP/LDAPS</td><td><a href="https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/">Microsoft AD Docs</a></td></tr>
    <tr><td>Okta</td><td>SAML 2.0</td><td><a href="https://developer.okta.com/docs/">Okta Developer Docs</a></td></tr>
    <tr><td>Azure AD</td><td>OpenID Connect</td><td><a href="https://learn.microsoft.com/en-us/azure/active-directory/">Azure AD Docs</a></td></tr>
  </table>

  <h2>Network Configuration</h2>
  <p>Ensure the following ports are open in your firewall:</p>
  <table>
    <tr><th>Port</th><th>Protocol</th><th>Purpose</th></tr>
    <tr><td>443</td><td>TCP</td><td>Web interface and API</td></tr>
    <tr><td>4172</td><td>TCP/UDP</td><td>PCoIP streaming</td></tr>
    <tr><td>60443</td><td>TCP</td><td>Management plane</td></tr>
  </table>

  <p>For troubleshooting network issues, see <a href="/docs/troubleshooting/">Troubleshooting</a>.</p>
  <p>See also the <a href="https://www.teradici.com/web-help/pcoip_connection_manager_for_amazon_workspaces/">Teradici PCoIP Guide</a> for detailed protocol information.</p>
</main>
</body></html>""",

    "/docs/troubleshooting/": """<!DOCTYPE html>
<html><head><title>Troubleshooting - Anyware Manager</title></head>
<body>
<nav class="sidebar">
  <a href="/docs/">Home</a>
  <a href="/docs/installation/">Installation Guide</a>
  <a href="/docs/configuration/">Configuration</a>
  <a href="/docs/troubleshooting/">Troubleshooting</a>
</nav>
<main>
  <h1>Troubleshooting</h1>
  <p>This page covers common issues and their solutions. Make sure you've followed the <a href="/docs/installation/">Installation Guide</a> and <a href="/docs/configuration/">Configuration</a> steps correctly.</p>

  <h2>Service Won't Start</h2>
  <p>If the Anyware Manager service fails to start:</p>
  <pre><code># Check service logs
sudo journalctl -u anyware-manager -f

# Verify configuration syntax
sudo anyware-manager config validate

# Check port conflicts
sudo ss -tlnp | grep -E '443|4172|60443'</code></pre>

  <h2>Database Connection Errors</h2>
  <p>If you see database connection errors:</p>
  <ol>
    <li>Verify PostgreSQL is running: <code>sudo systemctl status postgresql</code></li>
    <li>Check credentials in <code>/etc/anyware-manager/config.yaml</code> (see <a href="/docs/configuration/">Configuration</a>)</li>
    <li>Test connectivity: <code>psql -h localhost -U anyware anyware_manager</code></li>
  </ol>

  <h2>TLS Certificate Issues</h2>
  <p>For certificate-related errors:</p>
  <pre><code># Verify certificate chain
openssl verify -CAfile /etc/ssl/certs/ca.crt /etc/ssl/certs/server.crt

# Check certificate expiry
openssl x509 -enddate -noout -in /etc/ssl/certs/server.crt</code></pre>

  <h2>Getting Help</h2>
  <p>If the above steps don't resolve your issue:</p>
  <ul>
    <li>Check the <a href="https://community.hp.com/anyware">Community Forum</a> for similar issues</li>
    <li>File a bug on <a href="https://github.com/anyware/manager/issues">GitHub Issues</a></li>
    <li>Contact <a href="https://support.hp.com">HP Support</a> for enterprise customers</li>
  </ul>

  <p>Return to the <a href="/docs/">documentation home page</a> for an overview of all available guides.</p>
</main>
</body></html>""",
}


class MockDocHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # Normalize path
        path = self.path.split("?")[0]
        if not path.endswith("/") and path.startswith("/docs"):
            path += "/"

        if path in PAGES:
            content = PAGES[path].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress server logs


def start_server(port=8765):
    server = HTTPServer(("127.0.0.1", port), MockDocHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Mock docs server running on http://127.0.0.1:{port}/docs/")
    server = HTTPServer(("127.0.0.1", port), MockDocHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
