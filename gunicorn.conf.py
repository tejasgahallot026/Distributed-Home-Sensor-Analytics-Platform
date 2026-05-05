bind = "0.0.0.0:$PORT"
workers = 3
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 120
keepalive = 5
