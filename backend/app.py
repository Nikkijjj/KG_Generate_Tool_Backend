from flask import Flask, jsonify
from flask_cors import CORS
from routes.login_api import login_bp
from routes.textPreprocess_api import textPreprocess_bp  # 导入 Blueprint
from routes.projectManage_api import projectManage_bp
from routes.dashboard_api import dashboard_bp
from routes.extractSample_bp import extractSample_bp
from routes.askAI_api import askAI_bp
from routes.utils_api import utils_bp
from config import Config
from extensions import mail
from routes.register_api import register_bp
from routes.llmGenKG_api import llmGenKG_bp

app = Flask(__name__)
app.config.from_object(Config)
mail.init_app(app)
CORS(app, supports_credentials=True, origins=["http://localhost:8087"])
# 注册 API
app.register_blueprint(login_bp, url_prefix='/api')
app.register_blueprint(register_bp, url_prefix='/api')
app.register_blueprint(utils_bp, url_prefix='/api')
app.register_blueprint(textPreprocess_bp, url_prefix='/api')
app.register_blueprint(projectManage_bp, url_prefix='/api')
app.register_blueprint(askAI_bp, url_prefix='/api')
app.register_blueprint(dashboard_bp)
app.register_blueprint(extractSample_bp, url_prefix='/api')
app.register_blueprint(llmGenKG_bp, url_prefix='/api')



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)  # 运行 Flask 服务器
