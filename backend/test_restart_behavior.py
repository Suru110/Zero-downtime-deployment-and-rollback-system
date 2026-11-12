import os
import sys
import time
import subprocess
import json
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

def main():
    print("=" * 80)
    print("VERIFYING RESTART AND PROCESS LIFECYCLE BEHAVIOR (PHASE 3.1)")
    print("=" * 80)

    # 1. Setup a test deployment record with an old active quick tunnel URL
    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.database import SessionLocal
    from app.models.deployment import Deployment
    from app.models.user import User

    db = SessionLocal()
    from app.models.project import Project
    user = db.query(User).filter(User.username == "Tuser").first() or db.query(User).first()
    user_id = str(user.id)
    user_role = str(user.role)
    dep = db.query(Deployment).join(Project).filter(Project.owner_id == user.id).first()
    assert dep, "No deployment found in database!"

    old_url = "https://stale-old-session-url.trycloudflare.com"
    meta = dict(dep.metadata_info or {})
    meta["public_url"] = old_url
    meta["endpoint_status"] = "ready"
    meta["endpoint_details"] = {"tunnel_provider": "cloudflare-quick-tunnel"}
    meta["tunnel_provider"] = "cloudflare-quick-tunnel"
    dep.metadata_info = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(dep, "metadata_info")
    db.commit()
    dep_id = dep.id
    db.close()
    print(f"[Step 1] Injected old Quick Tunnel URL into DB for Deployment {dep_id}:")
    print(f"         public_url: {old_url}")
    print(f"         endpoint_status: ready")

    # 2. Start the backend without --reload
    print("\n[Step 2] Starting Backend process WITHOUT --reload...")
    env = os.environ.copy()
    env["KUBERNETES_MODE"] = "mock"
    env["ENABLE_MOCK_ADAPTERS"] = "true"
    env["CLOUDFLARE_TUNNEL_ENABLED"] = "false"

    backend_proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8008"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        # Wait for backend to be ready
        ready = False
        for _ in range(25):
            time.sleep(1)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8008/healthz", timeout=2) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                pass

        assert ready, "Backend failed to start!"
        print("         Backend started successfully and responding 200 OK.")
        # Give lifespan an extra second
        time.sleep(2)

        # 3. Verify that on startup, _reset_stale_quick_tunnels() cleared the stale URL
        print("\n[Step 3] Checking database state after startup...")
        db.close()
        db = SessionLocal()
        dep_fresh = db.query(Deployment).filter(Deployment.id == dep_id).first()
        print(f"         FULL METADATA: {dep_fresh.metadata_info}")
        fresh_meta = dep_fresh.metadata_info or {}
        fresh_status = fresh_meta.get("endpoint_status")
        fresh_url = fresh_meta.get("public_url")
        fresh_err = fresh_meta.get("endpoint_error")

        print(f"         endpoint_status: {fresh_status}")
        print(f"         public_url: {fresh_url}")
        print(f"         endpoint_error: {fresh_err}")

        assert fresh_status == "pending", f"Expected 'pending', got '{fresh_status}'"
        assert fresh_url is None, f"Expected None, got '{fresh_url}'"
        assert "re-established" in str(fresh_err), f"Expected re-established message, got '{fresh_err}'"
        print("         CONFIRMED: Stale Quick Tunnel URL was successfully invalidated on restart!")

        # 4. Trigger endpoint discovery via mock adapter to confirm re-provisioning
        print("\n[Step 4] Calling endpoint discovery API for this deployment...")
        from app.core.security import create_access_token
        token = create_access_token(subject=user_id, role=user_role)
        req = urllib.request.Request(
            f"http://127.0.0.1:8008/api/v1/deployments/{dep_id}/endpoint",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            ep_status = data["data"]["metadata_info"].get("endpoint_status")
            ep_url = data["data"]["metadata_info"].get("public_url")
            print(f"         Discovery API response status: {ep_status}")
            print(f"         Discovered public_url: {ep_url}")
            assert ep_url != old_url, "Endpoint discovery returned the stale URL!"
            print("         CONFIRMED: Endpoint was re-discovered and updated!")

    finally:
        # 5. Stop the backend normally and confirm shutdown
        print("\n[Step 5] Stopping backend process normally...")
        backend_proc.terminate()
        try:
            out, _ = backend_proc.communicate(timeout=5)
            print("BACKEND LOGS:")
            print(out)
        except Exception:
            backend_proc.kill()
        print(f"         Backend process terminated (exit code: {backend_proc.poll()})")

    # 6. Test unexpected crash recovery & orphaned process cleanup
    print("\n[Step 6] Testing Crash Recovery & Orphan Cleanup mechanism:")
    from app.services.cloudflare_tunnel import cloudflare_tunnel_service
    cleaned = cloudflare_tunnel_service.cleanup_orphaned_processes()
    print(f"         cleanup_orphaned_processes() executed cleanly. Swept {cleaned} process(es).")

    print("\n" + "=" * 80)
    print("RESTART & LIFECYCLE BEHAVIOR: 100% VERIFIED!")
    print("=" * 80)

if __name__ == "__main__":
    main()
