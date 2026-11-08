FROM node:24-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends bash ca-certificates git ripgrep \
  && rm -rf /var/lib/apt/lists/*
RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent \
  && npm install -g agent-browser --with-deps \
  && pi install npm:pi-agent-browser-native \
  && pi install npm:pi-mcp-adapter \
  && pi install npm:pi-subagents \
  && pi install npm:context-mode \
  && pi install npm:@juicesharp/rpiv-ask-user-question \
  && pi install npm:@juicesharp/rpiv-todo \
#  && pi install npm:@plannotator/pi-extension \
  && pi install npm:billion-context \
  && pi install npm:@postman/postman-plugin \
  && pi install npm:@dietrichgebert/ponytail \
  && pi install npm:cc-safety-net \
  && pi install npm:pi-lens \
  && pi install npm:pi-advisor-flow \
  && pi install npm:pi-memory
WORKDIR /workspace
# ENTRYPOINT ["pi"]
