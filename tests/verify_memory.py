import os
import shutil
import unittest
from unittest.mock import MagicMock, patch
from src.memory.profile_manager import ProfileManager, LocalProfileStorage, GCSProfileStorage

class TestProfileManager(unittest.TestCase):
    
    def setUp(self):
        # Clean up profiles directory before tests
        if os.path.exists("test_profiles"):
            shutil.rmtree("test_profiles")
        
    def tearDown(self):
        # Clean up after tests
        if os.path.exists("test_profiles"):
            shutil.rmtree("test_profiles")

    def test_local_storage(self):
        """Test LocalProfileStorage and ProfileManager in local mode."""
        print("\nTesting Local Storage...")
        os.environ["APP_ENV"] = "local"
        
        # Initialize manager with a specific test storage path directly or via env?
        # ProfileManager uses "APP_ENV" to pick backend.
        # LocalProfileStorage uses defaults, let's patch it or rely on it creating "profiles" dir?
        # The code hardcodes `base_dir="profiles"`. For test safety let's patch LocalProfileStorage
        
        with patch("src.memory.profile_manager.LocalProfileStorage") as MockLocal:
            # We want to test the REAL LocalProfileStorage logic, but maybe redirect the dir?
            # Let's just modify the class for the test or trust the "profiles" dir.
            # Actually, let's trust "profiles" dir but clean it up.
            pass

        # Real test on "profiles" dir
        user_id = "test_user_local"
        pm = ProfileManager(user_id)
        
        # Verify default state
        self.assertIsInstance(pm.storage, LocalProfileStorage)
        
        # Update profile
        pm.update_key_insight("vision", "To change the world locally")
        
        # Verify file exists
        expected_path = os.path.join("profiles", f"{user_id}_profile.json")
        self.assertTrue(os.path.exists(expected_path))
        
        # Verify content
        with open(expected_path, "r", encoding="utf-8") as f:
            data = f.read()
            self.assertIn("To change the world locally", data)
            
        print("Local Storage Test Passed!")

    @patch("src.memory.profile_manager.storage")
    def test_gcs_storage(self, mock_storage):
        """Test GCSProfileStorage and ProfileManager in production mode."""
        print("\nTesting GCS Storage...")
        os.environ["APP_ENV"] = "production"
        os.environ["GCS_BUCKET_NAME"] = "test-bucket"
        
        # Mock GCS Client and Bucket
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        
        mock_storage.Client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        
        # Setup mock blob behavior
        mock_blob.exists.return_value = False # First load returns empty
        
        user_id = "test_user_gcs"
        pm = ProfileManager(user_id)
        
        self.assertIsInstance(pm.storage, GCSProfileStorage)
        
        # Update profile
        pm.update_key_insight("mission", "To fly to the cloud")
        
        # Verify save called
        mock_bucket.blob.assert_called_with(f"profiles/{user_id}/soul_profile.json")
        mock_blob.upload_from_string.assert_called_once()
        
        # Check args
        args, kwargs = mock_blob.upload_from_string.call_args
        self.assertIn("To fly to the cloud", args[0])
        
        print("GCS Storage Test Passed!")

if __name__ == "__main__":
    unittest.main()
