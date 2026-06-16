import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from dispatch.app import DispatchApp

async def capture():
    # Setup a temporary data root to avoid dependency on real environment
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        dispatch_home = tmp_path / ".dispatch"
        dispatch_home.mkdir()
        (dispatch_home / "jobs").mkdir()
        (dispatch_home / "installed_version").write_text("1.0.0", encoding="utf-8")
        
        os.environ["DISPATCH_DATA_ROOT"] = tmp_dir
        
        app = DispatchApp()
        # We need a large enough size to show the full dashboard nicely
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.0) # Wait for animations/refreshes
            app.save_screenshot("home_screen.svg")
            print("Home screen captured to home_screen.svg")

if __name__ == "__main__":
    asyncio.run(capture())
