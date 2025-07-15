#!/usr/bin/env python3
"""
Reproduction script for fastapi_websocket_pubsub packaging issue.

This script demonstrates the original issue with version 1.0.1 and validates
that the fix in version 1.0.2 resolves the problem.

Original issue: Installing fastapi_websocket_pubsub[all]==1.0.1 with pip >=25.0
fails because the wheel's METADATA lists 'tls-cert-refresh-period' as a runtime
requirement, but this package doesn't exist on PyPI.

Bug report: https://github.com/permitio/fastapi_websocket_pubsub/issues/...
"""

import subprocess
import sys
import tempfile
import shutil
import os
from pathlib import Path

def run_command(cmd, cwd=None, check=True):
    """Run a command and return the result."""
    print(f"Running: {cmd}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            cwd=cwd,
            check=check
        )
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print(f"STDOUT:\n{e.stdout}")
        print(f"STDERR:\n{e.stderr}")
        if check:
            raise
        return e

def test_package_installation(package_spec, should_succeed=True):
    """Test installing a package specification."""
    print(f"\n{'='*60}")
    print(f"Testing installation: {package_spec}")
    print(f"Expected to {'succeed' if should_succeed else 'fail'}")
    print(f"{'='*60}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        venv_path = Path(tmpdir) / "test_env"
        
        # Create virtual environment
        run_command(f"python3 -m venv {venv_path}")
        
        # Activate and upgrade pip
        activate_cmd = f"source {venv_path}/bin/activate"
        run_command(f"{activate_cmd} && pip install --upgrade pip")
        
        # Try to install the package
        install_cmd = f"{activate_cmd} && pip install {package_spec}"
        result = run_command(install_cmd, check=False)
        
        success = result.returncode == 0
        
        if success == should_succeed:
            print(f"✓ Test passed: Installation {'succeeded' if success else 'failed'} as expected")
            return True
        else:
            print(f"✗ Test failed: Installation {'succeeded' if success else 'failed'} but expected {'success' if should_succeed else 'failure'}")
            return False

def test_built_package():
    """Test the locally built package."""
    print(f"\n{'='*60}")
    print("Testing locally built package (1.0.2)")
    print(f"{'='*60}")
    
    # Find the built wheel
    dist_dir = Path("dist")
    if not dist_dir.exists():
        print("✗ No dist directory found. Please build the package first with 'python -m build'")
        return False
    
    wheel_files = list(dist_dir.glob("*.whl"))
    if not wheel_files:
        print("✗ No wheel files found in dist directory")
        return False
    
    wheel_file = wheel_files[0]
    print(f"Testing wheel: {wheel_file}")
    
    return test_package_installation(f"{wheel_file}[all]", should_succeed=True)

def main():
    """Main function to run all tests."""
    print("FastAPI WebSocket PubSub Packaging Issue Reproduction Script")
    print("=" * 60)
    
    # Test results
    tests = []
    
    # Test 1: Try to install the problematic 1.0.1 version
    print("\nTest 1: Installing fastapi_websocket_pubsub[all]==1.0.1")
    print("This may or may not fail depending on PyPI's current state")
    result1 = test_package_installation("fastapi_websocket_pubsub[all]==1.0.1", should_succeed=False)
    tests.append(("1.0.1 installation", result1))
    
    # Test 2: Test the locally built 1.0.2 version
    print("\nTest 2: Testing locally built package (1.0.2)")
    result2 = test_built_package()
    tests.append(("1.0.2 local build", result2))
    
    # Test 3: Install without extras to verify base package works
    print("\nTest 3: Installing base package without extras")
    result3 = test_package_installation("fastapi_websocket_pubsub==1.0.1", should_succeed=True)
    tests.append(("Base package 1.0.1", result3))
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    for test_name, result in tests:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in tests)
    
    if all_passed:
        print("\n🎉 All tests passed! The packaging issue has been resolved.")
    else:
        print("\n❌ Some tests failed. Please check the output above.")
        
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())