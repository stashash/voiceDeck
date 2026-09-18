FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM maven:3.9.9-eclipse-temurin-21 AS backend
WORKDIR /app
COPY backend/pom.xml ./
RUN mvn -q dependency:go-offline
COPY backend/src ./src
COPY --from=frontend /app/dist ./src/main/resources/webroot
RUN mvn -q verify
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=backend /app/target/voicedeck-1.0.0.jar /app/app.jar
RUN mkdir /app/data /models /native && chown -R 10001:10001 /app
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-XX:+UseZGC", "-XX:+ZGenerational", "-XX:MaxRAMPercentage=70", "-cp", "/app/app.jar:/native/*", "local.voicedeck.Main"]
