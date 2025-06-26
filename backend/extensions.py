from flask_mail import Mail
import redis

mail = Mail()

# 用于全局共享的 Redis 实例
r = redis.StrictRedis(host='localhost', port=6379, decode_responses=True)
