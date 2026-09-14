import sys
import httpx
import json

def upload_to_gist(github_token: str, gist_filename: str, content: str):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    # 1. Search for an existing gist with this filename or a generic "EdgeTunnel Prober Custom Subs" gist
    GIST_DESCRIPTION = "EdgeTunnel Prober Custom Subs"
    with httpx.Client(timeout=30) as client:
        # Get user's gists
        resp = client.get("https://api.github.com/gists", headers=headers)
        if resp.status_code != 200:
            print(f"Failed to fetch gists: {resp.text}")
            return None
            
        gists = resp.json()
        target_gist_id = None
        
        for gist in gists:
            if gist.get("description") == GIST_DESCRIPTION:
                target_gist_id = gist["id"]
                break
                
        payload = {
            "description": GIST_DESCRIPTION,
            "public": True,
            "files": {
                gist_filename: {
                    "content": content
                }
            }
        }
                
        if target_gist_id:
            # Update existing gist
            patch_resp = client.patch(f"https://api.github.com/gists/{target_gist_id}", headers=headers, json=payload)
            if patch_resp.status_code == 200:
                print("Updated gist successfully.")
                res_data = patch_resp.json()
                raw_url = res_data["files"][gist_filename]["raw_url"]
                import re
                return re.sub(r'(/raw/)[^/]+/(.*)', r'\1\2', raw_url)
            else:
                print(f"Failed to update gist: {patch_resp.text}")
                return None
        else:
            # Create new gist
            post_resp = client.post("https://api.github.com/gists", headers=headers, json=payload)
            if post_resp.status_code == 201:
                print("Created gist successfully.")
                res_data = post_resp.json()
                raw_url = res_data["files"][gist_filename]["raw_url"]
                import re
                return re.sub(r'(/raw/)[^/]+/(.*)', r'\1\2', raw_url)
            else:
                print(f"Failed to create gist: {post_resp.text}")
                return None

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: gist_uploader.py <token> <filename> <filepath>")
        sys.exit(1)
        
    token = sys.argv[1]
    filename = sys.argv[2]
    filepath = sys.argv[3]
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        if not content.strip():
            print("File is empty, skipping upload.")
            sys.exit(0)
            
        url = upload_to_gist(token, filename, content)
        if url:
            print(f"GIST_URL={url}")
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
