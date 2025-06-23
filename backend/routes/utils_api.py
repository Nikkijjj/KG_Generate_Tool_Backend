import jwt
from flask import Blueprint, request, jsonify

# 定义 Blueprint
utils_bp = Blueprint('utils', __name__)

SECRET_KEY = 'your_secure_secret_key_here'
AVATAR_URL = 'https://s11.ax1x.com/2023/12/15/pihx4js.jpg'

def getUserName(token):
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    user_name = payload.get('username')
    return user_name

# 获取token中用户信息接口
@utils_bp.route('/util/getUserInfo', methods=['GET'])
def get_user_info():
    # 从请求头获取 Authorization: Bearer <token>
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'msg': '缺少或格式错误的Token', 'code': 401}), 401

    token = auth_header.split(' ')[1]

    try:
        # 解析 token，获取 payload
        user_name = getUserName(token)
        if not user_name:
            return jsonify({'msg': 'Token中缺少用户名信息', 'code': 400}), 400

        return jsonify({
            'msg': '操作成功',
            'status': 200,
            'data': {
                'userName': user_name,
                'nickName': user_name,
                'avatar': AVATAR_URL
            }
        })

    except jwt.ExpiredSignatureError:
        return jsonify({'msg': 'Token已过期', 'code': 401})
    except jwt.InvalidTokenError:
        return jsonify({'msg': '无效的Token', 'code': 401})
    except Exception as e:
        print(f"[解析Token异常] {str(e)}")
        return jsonify({'msg': '服务器错误', 'code': 500})
