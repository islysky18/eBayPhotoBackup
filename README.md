# eBay Listing Photo Backup

A Python tool to automatically backup all your eBay listing photos with auto-refresh token support. The script downloads images and organizes them by SKU, creating a comprehensive backup of all your eBay listing photos.

## Features

- Downloads all images from your eBay listings (active, ended, and modified)
- Organizes images by SKU (or item ID if no SKU) in structured folders
- Automatic OAuth token refresh when expired (no manual token updates needed)
- Creates a detailed CSV log of all image URLs and metadata
- Smart handling of:
  - Multiple images per listing
  - Pagination and rate limits
  - Failed download retries
  - Token expiration and refresh

Note: This project includes two similar scripts: `ebay_all_listings_auto_refresh.py` (recommended) and `ebay_all_listings_by_sku.py` (older version). Both have auto-refresh capability, but we recommend using `ebay_all_listings_auto_refresh.py` as it's the more maintained version.

## Prerequisites

- Python 3.6 or higher
- eBay Developer Account
- eBay Application Keys

## Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
cd eBayPhotoBackup
```

2. Install required Python packages:
```bash
pip install requests python-dateutil
```

## Setup

1. Create an eBay application at [eBay Developer Portal](https://developer.ebay.com/)

2. Create the following files in the project directory with your eBay credentials:

   - `client_id.txt`: Your eBay application client ID
   - `client_secret.txt`: Your eBay application client secret
   - `ru_name.txt`: Your eBay RuName

3. Get your initial access token using the OAuth manager:
```bash
python ebay_oauth_manager.py auth-url
```
   - Open the URL in your browser
   - Authorize the application
   - Copy the code from the redirected URL
```bash
python ebay_oauth_manager.py exchange <YOUR-AUTH-CODE>
```

This will create:
   - `accessToken.txt`: Your eBay access token
   - `refresh_token.txt`: Your refresh token

## Usage

### Running the Script
```bash
python ebay_all_listings_auto_refresh.py
```
The script will automatically refresh the token when it expires and continue downloading your images.

### Configuration

You can modify these settings in the scripts:
- `START_DATE`: First date to fetch listings from
- `ENTRIES_PER_PAGE`: Number of listings per API call (max 200)
- `SLEEP_BETWEEN_CALLS`: Delay between API calls
- `DOWNLOAD_TIMEOUT`: Image download timeout
- `DOWNLOAD_RETRIES`: Number of retry attempts for failed downloads

## Output Structure

The script organizes your eBay listing photos in a clean directory structure:

```
out_all/
├── image_urls.csv        # Complete log of all images with metadata
└── images_by_sku/        # Images organized by SKU
    ├── SKU1/            # One folder per SKU
    │   ├── SKU1.jpg     # Single image
    │   └── SKU1_2.jpg   # Additional images numbered
    └── SKU2/
        └── SKU2.jpg
```

## Token Management Tools

The project includes two helper tools for OAuth token management:

### Initial Setup
```bash
# 1. Get the authorization URL
python ebay_oauth_manager.py auth-url

# 2. After authorizing in browser, exchange the code
python ebay_oauth_manager.py exchange YOUR-AUTH-CODE
```

### Maintenance (if needed)
```bash
# Test if your token is working
python ebay_oauth_manager.py getuser

# Manually refresh token (rarely needed as script auto-refreshes)
python ebay_oauth_manager.py refresh
```

## Security Notes

Never commit these files to version control:
- `accessToken.txt`
- `refresh_token.txt`
- `client_id.txt`
- `client_secret.txt`
- `ru_name.txt`
- `token_meta.json`

## Troubleshooting

1. **Token Errors**: If you get token errors, try:
   ```bash
   python ebay_oauth_manager.py refresh
   ```

2. **Rate Limits**: If you hit rate limits, increase `SLEEP_BETWEEN_CALLS`

3. **Download Issues**: For slow connections, increase `DOWNLOAD_TIMEOUT`

## Contributing

Feel free to submit issues and pull requests.

## License

[Your chosen license]