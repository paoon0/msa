# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.12.8-slim AS base

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --prefix="/install" -r requirements.txt

FROM base
WORKDIR /loadgen
COPY --from=builder /install /usr/local
# proto スタブ + ロードジェネレータ本体
COPY demo_pb2.py demo_pb2_grpc.py loadgen.py ./

ENTRYPOINT ["python", "-u", "loadgen.py"]
