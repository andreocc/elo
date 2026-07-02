import subprocess, sys

# ── PyPI ──
with open('/root/obsidian/Pessoal/Chaves.md', 'rb') as f:
    raw = f.read()
idx = raw.find(b'pypi-')
end = raw.find(b'`', idx)
token = raw[idx:end].decode().strip()
with open('/root/.pypirc', 'w') as f:
    f.write('[distutils]\nindex-servers = pypi\n\n[pypi]\nusername = __token__\npassword = ' + token + '\n')

r = subprocess.run(['twine', 'upload', 'dist/*'], cwd='/root/dev/elo/py', capture_output=True, text=True, timeout=60)
print('PyPI:', r.stdout[-200:])
if r.returncode != 0:
    print('STDERR:', r.stderr[-200:])

# ── Git ──
r = subprocess.run(['git', 'add', '-A'], cwd='/root/dev/elo')
r = subprocess.run(['git', 'commit', '-m', 'v0.4.7 — segurança: result signing, rate limit, broadcast loop fix, bug send_task match'], cwd='/root/dev/elo', capture_output=True, text=True)
print('Commit:', r.stdout)

idx2 = raw.find(b'ghp_')
end2 = raw.find(b'`', idx2)
token2 = raw[idx2:end2].decode()
url = 'https://andreocc:' + token2 + '@github.com/andreocc/elo.git'
subprocess.run(['git', 'remote', 'set-url', 'origin', url], cwd='/root/dev/elo')
r = subprocess.run(['git', 'push'], cwd='/root/dev/elo', capture_output=True, text=True, timeout=30)
print('Push:', (r.stdout + r.stderr)[-200:])
subprocess.run(['git', 'remote', 'set-url', 'origin', 'https://github.com/andreocc/elo.git'], cwd='/root/dev/elo')
