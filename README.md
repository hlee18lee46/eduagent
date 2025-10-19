docker desktop enable model-runner --tcp 12434

docker version

docker desktop enable model-runner --tcp 12434
docker model run ai/smollm2
# type anything; exit with: /bye

# 1) Use the Model Runner endpoint
export OPENAI_BASE_URL="http://localhost:12434/engines/llama.cpp/v1"
export OPENAI_API_KEY="sk-local-anything"

# 2) (Re)start Flask from this same shell
python app.py




export OPENAI_BASE_URL="http://localhost:12434/engines/llama.cpp/v1"
export OPENAI_API_KEY="sk-local-anything"
export MODEL_NAME="ai/smollm2"
python app.py


OPENAI_BASE_URL=http://localhost:8080/v1
MODEL_NAME=gpt-3.5-turbo   # llama.cpp often expects this placeholder id
OPENAI_API_KEY=sk-local-anything