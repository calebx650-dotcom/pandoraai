
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

class ResearchModule:
    def research(self, question):
        print(f"  -> [Research] Starting web search for: '{question}'")
        try:
            # Perform the search and get the top result
            with DDGS() as ddgs:
                results = list(ddgs.text(question, max_results=1))
                if not results:
                    print("  -> [Research] No search results found.")
                    return []
                
                top_result = results[0]
                url = top_result['href']
                print(f"  -> [Research] Found source: {url}")

            # Fetch the content from the URL
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status() # Raise an exception for bad status codes

            # Parse the HTML and extract text
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script_or_style in soup(["script", "style"]):
                script_or_style.decompose()

            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)

            print(f"  -> [Research] Successfully extracted text from source.")
            return [clean_text]

        except Exception as e:
            print(f"  -> [Research] An error occurred: {e}")
            return []
