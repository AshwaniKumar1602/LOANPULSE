import os
from app import create_app

env = os.getenv("FLASK_ENV", "development").lower()
app = create_app(env)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    # Production constraint: debug strictly False
    app.run(host="0.0.0.0", port=port, debug=False)
