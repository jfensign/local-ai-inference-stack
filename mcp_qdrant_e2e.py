#!/usr/bin/env python3
"""Sequential MCP stdio E2E test for mcp-server-qdrant (offline, FastEmbed)."""
import json
import os
import subprocess
import sys
import uuid

env = dict(os.environ,
    QDRANT_URL='http://qdrant:6333',
    FASTEMBED_CACHE_PATH='/models/.hf/hub',
    HF_HUB_OFFLINE='1')

p = subprocess.Popen(
    ['uvx', 'mcp-server-qdrant'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=env,
)

def send(msg):
    p.stdin.write(json.dumps(msg) + '\n')
    p.stdin.flush()

def recv():
    line = p.stdout.readline()
    if not line:
        err = p.stderr.read()
        raise RuntimeError(f'EOF on stdout. stderr: {err[:2000]}')
    return json.loads(line)

def rpc(rid, method, params=None):
    send({'jsonrpc': '2.0', 'id': rid, 'method': method, **({'params': params} if params else {})})
    while True:
        m = recv()
        if m.get('id') == rid:
            if 'error' in m:
                raise RuntimeError(f'RPC error {method}: {m["error"]}')
            return m['result']

try:
    init = rpc(1, 'initialize', {
        'protocolVersion': '2024-11-05',
        'capabilities': {},
        'clientInfo': {'name': 'e2e-test', 'version': '0.1'},
    })
    print('INIT:', init['serverInfo']['name'], init['serverInfo'].get('version'))

    send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    p.stdin.flush()

    tools = rpc(2, 'tools/list')
    names = sorted(t['name'] for t in tools['tools'])
    print('TOOLS:', names)

    # qdrant-find against directive
    r = rpc(3, 'tools/call', {
        'name': 'qdrant-find',
        'arguments': {'query': 'hf-downloader model pull directive', 'collection_name': 'memories'},
    })
    print('FIND1_IS_ERROR:', r.get('isError'))
    print('FIND1:', json.dumps(r['content'])[:600])

    # qdrant-store a fresh point
    marker = f'offline-e2e-{uuid.uuid4().hex[:8]}'
    r = rpc(4, 'tools/call', {
        'name': 'qdrant-store',
        'arguments': {
            'information': f'{marker}: post-fix verification that store+find round-trip works offline',
            'collection_name': 'memories',
            'metadata': {'project': 'llama-stack', 'verified': True},
        },
    })
    print('STORE_IS_ERROR:', r.get('isError'))
    print('STORE:', json.dumps(r['content'])[:300])

    # qdrant-find for the new point
    r = rpc(5, 'tools/call', {
        'name': 'qdrant-find',
        'arguments': {'query': marker, 'collection_name': 'memories'},
    })
    print('FIND2_IS_ERROR:', r.get('isError'))
    print('FIND2:', json.dumps(r['content'])[:600])

    ok = (not r.get('isError')) and marker in json.dumps(r['content'])
    print('E2E_RESULT:', 'PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)
finally:
    p.stdin.close()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()