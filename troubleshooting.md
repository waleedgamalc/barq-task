# Troubleshooting journal

This file documents the investigation process: symptoms observed, hypotheses formed, commands run, results (including failed attempts), root causes, fixes, and retest evidence.


## Entry #1: NGINX upstream port mismatch / 11/09/26 / 22:11


- Symptom: curl http://localhost:8080/ returns curl: (52) Empty reply from server. All 5 containers show Up in docker compose ps, so no container had crashed.

Hypothesis: NGINX is misrouting requests to the wrong port on the Flask backends.

Command or test: `docker exec nginx cat /etc/nginx/nginx.conf | grep -n "proxy_pass\|8080\|8081"`

- Actual output: ```text
10:        server app-01:8081 max_fails=0; => here is the mistake it should be port 8080 not 8081
11:        server app-02:8080 max_fails=0;
17:        proxy_pass http://application_pool;
```

Compared against app startup logs: `docker compose logs app-01 | grep "Running on"`

app-01  |  * Running on http://127.0.0.1:8080

`docker compose logs app-02 | grep "Running on"`

app-02  |  * Running on http://127.0.0.1:8080

- Failed attempt and what changed your thinking: 

  `docker compose restart nginx
  `curl http://localhost:8080/`
  curl: (52) Empty reply from server
 
- Given that The App's listening ports are correct and the nginx upstreams are ok then i thought to test if nginx can connect to apps or not.


## Entry #2: NGINX cannot reach app-01, app-02 / 11/09/26 / 23:01


- Symptoms: `docker exec nginx curl http://app-01:8080/`

  curl: (7) Failed to connect to app-01 port 8080 after 1 ms: Could not connect to server

the issue that nginx cannot reach the apps given though i've already checked the listening ports on both App-01 and App-02 

- Hypothesis: Either a Docker network isolation problem, or the Flask app is not listening on an interface reachable from other containers.

- Command or test: 

first i want to make sure they are in the same network: `docker network inspect barq-assessment_frontend | grep -A3 '"Name"'`

- Actual output: 
```         "Name": "barq-assessment_frontend",
        "Id": "bfa6805fdb455432c0a7847f282e1b73efb51a584d269498050de7752d62c970",
        "Created": "2026-09-11T14:26:24.783949097Z",
        "Scope": "local",
--
                "Name": "app-01",
                "EndpointID": "9eb73301083c70a5c1b27da0230fe1c2cd360d329a73a4c78562b9e71e08131a",
                "MacAddress": "72:ea:6a:da:54:da",
                "IPv4Address": "172.19.0.3/16",
--
                "Name": "nginx",
                "EndpointID": "5e9ae86b9f3a17b98f686718f4b89023301b88e3f3ad02ae7d7467759b121dc0",
                "MacAddress": "9a:67:83:61:d7:7d",
                "IPv4Address": "172.19.0.4/16",
--
                "Name": "app-02",
                "EndpointID": "8e22fbc39f114fc3c817bc815aeb8f392e90f45c68d19cfdd59fa7cea31d3d72",
                "MacAddress": "ca:0b:38:27:47:c8",
                "IPv4Address": "172.19.0.2/16",
```

- Root cause: `grep -n "app.run\|host=" app/server.py`

create_app().run(host=os.getenv("APP_HOST", "0.0.0.0")

First assumed the Flask code hardcoded app.run(host="127.0.0.1"). Checked and this was wrong, the code already used host="0.0.0.0":

 This failed hypothesis redirected the investigation from the application code to how the container's runtime environment is
 configured (docker-compose.yml).

by applying this command `grep -n "anchor\|&\|APP_HOST\|127.0.0.1\|0.0.0.0" docker-compose.yml`

``` 
2:x-app: &app
7:  environment: &app-env
8:    APP_HOST: "127.0.0.1"
12:    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
26:    ports: ["127.0.0.1:15432:5432"]
41:    ports: ["127.0.0.1:16379:6379"]
63:    ports: ["127.0.0.1:${PUBLIC_PORT:-8080}:81"]
``` 

A shared YAML anchor in docker-compose.yml, used by both app-01 and app-02, injected a host-binding environment variable set to 127.0.0.1 instead of 0.0.0.0, overriding the app's correct default at runtime. 127.0.0.1 only accepts connections from inside the same container, so nginx (a different container) was refused instantly even though it was on the same network.

- Fix: Changed the host-binding value inside the shared YAML anchor in docker-compose.yml from 127.0.0.1 to 0.0.0.0, applying the fix to both app-01 and app-02 from a single source.



- Retest evidence: `docker exec nginx curl -i http://app-01:8080/`

```
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   100 100   100   0     0 3810HTTP/1.1 200 OK-- --:--:-- --:--:--     0
9     0  --:--:-- --:--:-- --:--:-- 50000
Server: Werkzeug/3.1.8 Python/3.12.14
Date: Fri, 11 Sep 2026 19:16:00 GMT
Content-Type: application/json
Content-Length: 100
X-Instance-ID: app-01
X-Request-ID: 82e4c3f3d0b44af288e0e4b21777ecbb
Cache-Control: no-store
Connection: close

{"instance_id":"app-01","message":"Welcome to BARQ Systems","service":"barq-api","version":"2.0.0"}
```


## Entry #3: Listening port mismatch between nginx in compose file and nginx.conf file / 12/09/26 / 00:40


- Symptom: Even after fixing the app host-binding issue (Entry 2), NGINX still returned nothing:

  curl -i http://localhost:8080/
  curl: (52) Empty reply from server

- Hypothesis: A port mismatch between the host-container mapping in docker-compose.yml and the port NGINX actually listens on inside the container.

- Command or test:  `grep -n "ports:" -A2 docker-compose.yml`
  `docker exec nginx cat /etc/nginx/conf.d/default.conf | grep listen`


- Actual output:

  ports: ["127.0.0.1:${PUBLIC_PORT:-8080}:81"]
  ...
      listen       80;
      listen  [::]:80;

- Root cause: docker-compose.yml mapped the host port to container port 81, but NGINX listens on port 80 inside the container. The two numbers must match for the host-container port mapping to reach a real listener.

- Fix: Changed the ports: mapping for the nginx service in docker-compose.yml from :81 to :80 ("127.0.0.1:${PUBLIC_PORT:-8080}:80").


- Retest evidence:

  `docker compose up -d --force-recreate nginx`
  `docker port nginx`

  80/tcp -> 127.0.0.1:8080


  `curl -i http://localhost:8080/`

```HTTP/1.1 200 OK
Server: nginx/1.28.3
Date: Fri, 11 Sep 2026 21:21:53 GMT
Content-Type: application/json
Content-Length: 100
Connection: keep-alive
X-Instance-ID: app-01
X-Request-ID: 97d8859498bd28fa0e2a3509c017169d
Cache-Control: no-store

{"instance_id":"app-01","message":"Welcome to BARQ Systems","service":"barq-api","version":"2.0.0"}
```



## Entry #4: /ready endpoint issue related to port mismatching in app.env configurations / 12/09/26 / 17:52


- Symptom: `curl -i http://localhost:8080/ready`

HTTP/1.1 503 SERVICE UNAVAILABLE
Server: nginx/1.28.3
Date: Sat, 12 Sep 2026 17:52:21 GMT
Content-Type: application/json
Content-Length: 143
Connection: keep-alive
X-Instance-ID: app-01
X-Request-ID: 23ea1f40278fec53c8e34399fd149943
Cache-Control: no-store

{"dependencies":{"postgres":"unavailable","redis":"ready"},"instance_id":"app-01","service":"barq-api","status":"not_ready","version":"2.0.0"}

/health and /instance both returned 200 OK correctly, so the app process itself was alive, the failure was isolated to the postgres/redis dependency checks.


- Hypothesis: Same issue as Entry 3 (port mismatch): the app's configured connection ports for postgres/redis do not match the ports those services actually listen on.


 `docker compose logs app-01 | grep "configuration_loaded"`
  `docker compose logs postgres | grep "listening on"`
  `docker compose logs redis | grep "port="s`
  

```
app-01  | {"timestamp": "2026-09-12T17:11:50.526+00:00", "level": "INFO", "service": "barq-api", "event": "configuration_loaded", "database_url": "postgresql://barq_app:BarqLabOnly_7qN2vK8d@postgres:5433/barq_tasks", "redis_url": "redis://redis:6380/0"}
```

```
postgres  | 2026-09-12 17:11:50.444 UTC [42] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
postgres  | 2026-09-12 17:11:50.784 UTC [1] LOG:  listening on IPv4 address "0.0.0.0", port 5432
postgres  | 2026-09-12 17:11:50.784 UTC [1] LOG:  listening on IPv6 address "::", port 5432
postgres  | 2026-09-12 17:11:50.795 UTC [1] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"

```

```
redis  | 1:M 12 Sep 2026 17:11:48.500 * Running mode=standalone, port=6379.
```

App config used postgres:5433 and redis:6380, while postgres and redis logs showed them actually listening on their real default ports (5432 and 6379 respectively).


- Root cause: The app's DATABASE_URL / REDIS_URL environment variables in app.env pointed to the wrong ports (5433, 6380) instead of the real listening ports of postgres (5432) and redis (6379). Decision: fix the app config rather than the services, since postgres and redis were correctly using their standard defaults. 


- Fix: Updated DATABASE_URL to use port 5432 and REDIS_URL to use port 6379 in app.env, then recreated the app containers:
  
  `docker compose up -d --force-recreate app-01 app-02`

- Retest evidence: 

  `curl -i http://localhost:8080/ready`

  ```
  HTTP/1.1 503 SERVICE UNAVAILABLE
  Server: nginx/1.28.3
  Date: Sat, 12 Sep 2026 17:52:21 GMT
  Content-Type: application/json
  Content-Length: 143
  Connection: keep-alive
  X-Instance-ID: app-01
  X-Request-ID: 23ea1f40278fec53c8e34399fd149943
  Cache-Control: no-store

  {"dependencies":{"postgres":"unavailable","redis":"ready"},"instance_id":"app-01","service":"barq-api","status":"not_ready","version":"2.0.0"}

  ```

  - Partial fix confirmed: the redis port correction resolved the redis dependency ("redis":"ready"). The postgres dependency is still "unavailable" after using port 5432, so the root cause for postgres is not yet fully confirmed, investigation continues in Entry 5.

  - Remaining uncertainty: Redis dependency confirmed fixed. Postgres dependency still reports "unavailable" even after changing the port to 5432, root cause not yet identified. Possible causes to check next: credentials.


  - Root cause (postgres): Password mismatch between the value postgres was initialized with (docker-compose.yml, source of truth) and the value the app read from config/app.env (stale/incorrect copy).

  - Fix (postgres): Corrected the password of postgress user in config/app.env to match docker-compose.yml, then recreated the app containers.

  - Final retest evidence:

    `docker compose up -d --force-recreate app-01 app-02`
    `curl -i http://localhost:8080/ready`


   ```
    HTTP/1.1 200 OK
    {"dependencies":{"postgres":"ready","redis":"ready"},
    "instance_id":"app-01","status":"ready","version":"2.0.0"}
   ```


## Entry #5: Checking that the two backends are serving and the loadbalancing between them are working  / 13/09/26 / 00:31


- Symptom: All requests through NGINX returned the same backend identity

`for i in 1 2 3 4; do curl -s http://localhost:8080/instance; echo; done`

```
{"instance_id":"app-01","service":"barq-api","status":"ok","version":"2.0.0"}

{"instance_id":"app-01","service":"barq-api","status":"ok","version":"2.0.0"}

{"instance_id":"app-01","service":"barq-api","status":"ok","version":"2.0.0"}

{"instance_id":"app-01","service":"barq-api","status":"ok","version":"2.0.0"}
```

- Hypothesis: Maybe the app-02 is misconfigured and the nginx can't connect to it so it send all the traffic to app-01

`  docker exec nginx curl http://app-02:8080/instance`

- Actual output:

```
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0   0     0   0     0     0     0  --:--:-- --:--:-- --:--:--     0{"instance_id":"app-01","service":"barq-api","status":"ok","version":"2.0.0"}
100    78 100    78   0     0 14335     0  --:--:-- --:--:-- --:--:-- 19500
```

App-02 is working very well but even a direct request to app-02 returned instance_id: app-01,so the issue was in app-02 configurations in compose file.

- Command or test (continued):

`  grep -n "INSTANCE_ID\|&app\|<<: \*" docker-compose.yml`

- Actual output: 

```
2:x-app: &app
7:  environment: &app-env
49:    <<: *app
52:      <<: *app-env
53:      INSTANCE_ID: "app-01"
55:    <<: *app
58:      <<: *app-env

```

Both app-01 and app-02 blocks had INSTANCE_ID: "app-01", a copy/paste error left app-02's override unset to its own identity.

- Fix: Changed line 59 in docker-compose.yml from INSTANCE_ID: "app-01" to INSTANCE_ID: "app-02".

- Retest evidence:

`for i in 1 2 3 4; do curl -s http://localhost:8080/instance; echo; done`]

```
{"instance_id":"app-01","service":"barq-api","status":"ok","version":"2.0.0"}

{"instance_id":"app-02","service":"barq-api","status":"ok","version":"2.0.0"}

{"instance_id":"app-01","service":"barq-api","status":"ok","version":"2.0.0"}

{"instance_id":"app-02","service":"barq-api","status":"ok","version":"2.0.0"}
```


## Entry #6: App's Volume Issue and  port exposure problem in postgres and redis, and app health check typo issue  / 13/09/26 / 23:31


- Symptom: While reviewing docker-compose.yml against Part 2 requirements (before any live failure was observed), three separate configuration problems were found by inspection: 
  1- The PostgreSQL named volume was mounted at the wrong path.
  2- postgres and redis published host ports, which the task explicitly disallows.
  3- The app healthcheck targeted /healthz, a path that does not exist (confirmed earlier: "path": "/healthz", "status": 404 in the very first startup logs).

- Hypothesis: These were latent bugs that had not yet caused a visible symptom during earlier testing (all endpoints already worked because the app itself never depended on /healthz), but would fail Part 2 requirements and, in the volume's case, would silently lose data on the first container recreation performed in Part 3.


- Command or test: `cat docker-compose.yml`

- Actual output: 

```
  volumes:
    - postgres-data:/var/lib/postgresql/backup
  tmpfs: [/var/lib/postgresql/data]
  ...
  ports: ["127.0.0.1:15432:5432"]   # postgres
  ports: ["127.0.0.1:16379:6379"]   # redis
  ...
  healthcheck:
    test: [... "http://127.0.0.1:8080/healthz" ...]

```


- Failed attempt and what changed your thinking: found directly by reading the compose file against the PDF requirements, not by trial and error.


- Root cause: 

  1- Volume path mismatch: PostgreSQL actually stores its data at /var/lib/postgresql/data, but the named volume postgres-data was mounted at /var/lib/postgresql/backup instead. The real data directory was separately mounted as tmpfs (RAM-backed, wiped on every container stop/recreate), so the named volume was not actually protecting anything.

  2- Exposed ports: postgres and redis published ports to the host (even though scoped to 127.0.0.1), which the task requires not to do. They do not need a host port at all since app-01/app-02 reach them over the backend network by service name.

  3- Healthcheck path: the healthcheck called /healthz, but the app's actual liveness endpoint is /health. The healthcheck was silently failing (unhealthy) without being noticed because docker compose ps health status had not been checked until now.

- Fix:

  1- In docker-compose.yml, changed the postgres volume mount to postgres-data:/var/lib/postgresql/data and removed the tmpfs line entirely.

  2- Removed the ports: entries for both postgres and redis services completely.

  3- Changed the healthcheck URL in the shared x-app anchor from /healthz to /health.


- Retest evidence:

`docker compose down` 
`docker compose up -d --build`
`docker compose ps`


```
NAME       IMAGE                                                                                        COMMAND                  SERVICE    CREATED         STATUS                   PORTS
app-01     barq-assessment-app-01                                                                       "python -m app.server"   app-01     9 seconds ago   Up 8 seconds (healthy)   8080/tcp
app-02     barq-assessment-app-02                                                                       "python -m app.server"   app-02     9 seconds ago   Up 8 seconds (healthy)   8080/tcp
nginx      nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236    "/docker-entrypoint.…"   nginx      8 seconds ago   Up 7 seconds             127.0.0.1:8080->80/tcp
postgres   postgres:16-alpine@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685   "docker-ent
```

`curl -X POST http://localhost:8080/records -H "Content-Type: application/json" -d '{"title":"persistence test"}'`
`docker compose up -d --force-recreate postgres`
`curl http://localhost:8080/records`

```
{"instance_id":"app-02","records":[{"id":1,"title":"Review service readiness"},{"id":2,"title":"Document the operating procedure"},{"id":3,"title":"persistence test"}],"service":"barq-api","version":"2.0.0"}
```

The record created before recreating postgres is still present afterward, confirming the named volume now correctly persists data.





## Entry #7: Prohibting root priviledges  / 13/09/26 / 23:55


- Symptom: While reviewing the Dockerfile against Part 2 requirements ("Avoid root/privileged operation where practical"), found that app-01/app-02 containers run as root despite the Dockerfile creating a dedicated non-root user.


- Hypothesis: The Dockerfile sets up a non-root user correctly but something later overrides it back to root before the container starts.

- Command or test: 

  `cat Dockerfile`
  `docker exec app-01 whoami`
  `docker exec app-01 id`

- Actual output:

  RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
  ...
  COPY --chown=app:app app/ ./app/
  ...
  USER root
  EXPOSE 8080
  CMD ["python", "-m", "app.server"]

  $ docker exec app-01 whoami
  root
  $ docker exec app-01 id
  uid=0(root) gid=0(root) groups=0(root)

- Failed attempt and what changed your thinking: found directly by reading the Dockerfile against the task requirement, then confirmed live with whoami/id.

- Root cause: The Dockerfile correctly creates a non-root user (app, uid 10001) and even copies application files with the right ownership (--chown=app:app), but an explicit USER root line right before the CMD overrides all of that, so the container actually runs as root at runtime.


- Fix: Changed USER root to USER app in the Dockerfile.

- Retest evidence:

  `docker compose up -d --build --force-recreate app-01 app-02`
  `docker exec app-01 whoami`
    app
  `docker exec app-02 whoami`
    app

Both app containers now run as the non-root app user. No permission errors observed after the rebuild; endpoints re-verified working normally afterward.





## Entry #8: add restart policies and resource limits to all services  / 14/09/26 / 01:35

- Symptom: Reviewing docker-compose.yml against Part 2 requirements found two missing items (not a failure, a gap): no restart policy was set except restart: "no" on the apps, and no service had CPU/memory limits defined at all.

- Hypothesis: These are required configuration additions, not bugs to root-cause,the task explicitly requires "restart policies and resource limits" for all services.

- Command or test: `cat docker-compose.yml`

- Actual output: restart: "no" on the x-app anchor (app-01/app-02); no restart key at all on postgres, redis, or nginx; no deploy.resources.limits anywhere in the file.

- Failed attempt and what changed your thinking: a checklist gap identified directly from the PDF requirements, not discovered by testing.

- Root cause: missing configuration, not a defect with a root cause.

- Fix: Added to every service (via the shared x-app anchor for app-01/app-02, and individually for postgres, redis, nginx):

 ``` restart: unless-stopped
     deploy:
     resources:
      limits:
        cpus: "<value>"
        memory: "<value>"
        ```

  Chosen limits: app-01/app-02 = 0.5 CPU / 256M, postgres = 1.0 CPU / 512M (heavier due to read/write DB workload), redis = 0.3 CPU / 128M, nginx = 0.3 CPU / 64M. unless-stopped was chosen over always so a deliberate manual docker compose stop is respected and not automatically undone, while crashes/OOM kills still recover automatically.

- Retest evidence: 

  `docker compose up -d --force-recreate`
  `docker compose ps`
  all 5 containers Up, app-01/app-02/postgres/redis show (healthy)

  `docker stats --no-stream`
    nginx    3.39MiB / 64MiB
    postgres 18.41MiB / 512MiB
    redis    8.22MiB / 128MiB
    app-01   37.04MiB / 256MiB
    app-02   37.05MiB / 256MiB
  
  All memory limits are being enforced as configured (visible in the MEM USAGE / LIMIT column) and no container is being throttled or killed at current load.
