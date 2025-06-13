from flask import request, jsonify
import jwt


# 装饰器用于验证 JWT Token
def token_required(f):
    def decorator(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]  # 获取 Authorization 中的 token 部分
        if not token:
            return jsonify({'message': 'Token is missing!'}), 403

        try:
            # 解码 Token，验证其有效性
            payload = jwt.decode(token, "secret_key", algorithms=['HS256'])
            request.user_id = payload['user_id']  # 将用户 ID 添加到请求中
            request.username = payload['username']  # 将用户名添加到请求中
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 403
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 403

        return f(*args, **kwargs)

    return decorator
