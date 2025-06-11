#!/home/z31b4r1k3v0rk/case-karma-prod-chatbot.zeibari.net/venv/bin/python3
import sys, os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create log directory
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Set up error logging
error_log = os.path.join(log_dir, 'chatbot_error.log')

try:
    from flup.server.fcgi import WSGIServer
    from messenger_webhook import app
    
    if __name__ == '__main__':
        WSGIServer(app).run()
except Exception as e:
    import traceback
    with open(error_log, 'a') as f:
        f.write(f"\n\n--- New Error at {os.popen('date').read().strip()} ---\n")
        f.write(f"Error: {str(e)}\n")
        f.write(traceback.format_exc())
    
    # Also output error for web display
    print("Content-Type: text/html\n")
    print("<html><body>")
    print("<h1>FastCGI Application Error</h1>")
    print(f"<p>Error: {str(e)}</p>")
    print("</body></html>")
