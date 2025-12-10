import sys
import logging
from dotenv import load_dotenv
from astro_deploy_logic import AstroDeployer

def main():
    """
    Headless deployment script for the Google News Astro Blaster.
    This script is intended to be run by a CI/CD system.
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Load environment variables from .env file
    load_dotenv()
    
    try:
        # The AstroDeployer uses environment variables for configuration
        # and prints status updates to stdout by default.
        deployer = AstroDeployer()
        deployer.run()
        logging.info("Deployment script finished successfully.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"An error occurred during deployment: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
