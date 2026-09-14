# BARQ Systems - DevOps Internship Task
## Questions & Answers

### 1. What failed first? What proved the cause? Which failed attempt taught you something?
The first issue I found was that NGINX could not reach the Flask applications. Initially, I suspected that the Flask application was binding to localhost, but after checking the application configuration I found that it already used `0.0.0.0` by default. The actual problem was the `APP_HOST` environment variable in Docker Compose, which was overriding it with `127.0.0.1`.

I proved the root cause by changing `APP_HOST` to `0.0.0.0` and then testing connectivity from the NGINX container to the application container.

One failed attempt that helped me was restarting NGINX and testing the public endpoint. The result showed that the problem was not simply an NGINX configuration issue, which led me to test connectivity between the containers directly.

### 2. What patterns did the logs reveal? How did you avoid double-counting requests?
The logs revealed four separate failure windows rather than one continuous outage. The first incident was an NGINX connection failure to `app-02`. The second involved Redis timeouts affecting both application instances. The third was a PostgreSQL authentication failure affecting both instances. The fourth was an upstream timeout affecting the `/records` endpoint.

To avoid double-counting, I used the `request_id` as the correlation key and separated `dependency_error` events from their corresponding `http_request` events. I also removed exact duplicate log lines before processing the data.

### 3. How do requests flow? Why these ports, networks and readiness checks?
A client sends traffic to NGINX on the public port. NGINX is connected only to the frontend network and forwards requests to either `app-01` or `app-02` using Docker service names.

The application containers are connected to both the frontend and backend networks. PostgreSQL and Redis are connected only to the backend network, so they are not directly reachable from NGINX.

Inside the Docker network, the Flask applications listen on port `8080`, PostgreSQL on `5432`, and Redis on `6379`. NGINX listens on port `80` inside its container and is exposed through the public host port.

The `/health` endpoint checks whether the application process is alive, while `/ready` verifies that PostgreSQL and Redis are actually reachable.

### 4. Why these timeouts, retries, restart settings and resource limits?
The timeouts are intentionally bounded so that a failed dependency or backend does not hang requests indefinitely. The application health checks use short intervals and several retries to distinguish a temporary startup condition from a persistent failure.

The containers use an `unless-stopped` restart policy so unexpected failures can recover automatically while still respecting an intentional manual stop.

Resource limits are set according to the expected role of each service. PostgreSQL receives more CPU and memory because it handles database operations, while NGINX and Redis require fewer resources. These values are appropriate for this lab environment, but they should be adjusted in production using real workload measurements.

### 5. When should validation fail? What does green CI prove, or not prove?
Validation should fail whenever an important requirement is not satisfied, such as an unavailable endpoint, failed PostgreSQL or Redis readiness, incorrect network isolation, or an exposed prohibited host port.

A green CI run proves that the automated checks passed in the CI environment for that commit. However, it does not prove that every production scenario is handled correctly. It does not replace real failure testing, production-scale load testing, security testing, or infrastructure monitoring.

### 6. Which single points of failure remain? How would you fix them in production?
The main remaining single points of failure are PostgreSQL and Redis because there is only one instance of each. PostgreSQL storage is also on the same host, so a host-level failure could affect both the database and local backups.

In production, I would use a managed or highly available PostgreSQL deployment with replication and automated failover. For Redis, I would use a highly available Redis architecture if the application required Redis availability.

I would also store backups remotely, such as in object storage, instead of keeping them only on the same host.

### 7. What would you improve? How did you verify AI-assisted work?
I would improve the solution by adding centralized logging and monitoring, TLS, rate limiting or a WAF, stronger database least-privilege permissions, remote backups, and vulnerability scanning.

AI was used as an assistant during troubleshooting, scripting, and documentation, but I verified the work myself by running the commands, testing the environment, intentionally creating failures, and checking the results.

I did not rely on AI output without verification.
