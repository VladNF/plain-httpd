# 1. Architecture
Asynchronous approach was implemented with asyncore/asynchat modules

# 2. Running server
To run server with one worker type in shell <code>python httpd.py -r ./tests/ -w 1</code>

Use provided Docker container for running server in epoll-mode which available in CentOS. 
The server in the container is configure to run 4 workers (in docker-compose.yml)

# 3. Performance Tests
To measure performance the wrk util has been used

Below is one of the best results obtained.

````
$ :wrk -t8 -c100 --timeout 1s -d30s http://localhost/
Running 30s test @ http://localhost/
  8 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency    54.18ms   46.03ms 916.95ms   86.71%
    Req/Sec    76.39     43.30   300.00     69.52%
  8538 requests in 30.07s, 1.36MB read
  Socket errors: connect 0, read 8608, write 1, timeout 510
  Non-2xx or 3xx responses: 8538
Requests/sec:    283.90
Transfer/sec:     46.30KB
````
