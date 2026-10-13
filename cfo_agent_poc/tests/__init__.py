"""Regression tests for local bill parsing."""

import os

# server.py 导入时会读 cfo_agent_poc/.env（只补缺、不覆盖）。开发机上那份 .env 里有真实的
# DeepSeek 密钥，不先占住的话，测试入账后触发的后台分类会真的去调线上模型。
# 测试一律离线：在任何测试模块导入 server 之前把密钥置空。
os.environ["DEEPSEEK_API_KEY"] = ""
