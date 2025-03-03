from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# 生成随机数据
data_4k = os.urandom(4 * 1024)  # 4KB
data_150k = os.urandom(150 * 1024)  # 150KB

@app.route('/test', methods=['POST'])
def test():
    test_type = request.headers.get('Test-Type')
    if test_type == '1':
        # 测试类型1：不含数据，仅测算请求到响应的时间差
        return jsonify({'message': 'pong'})
    elif test_type == '2':
        # 测试类型2：发送4K数据，接收4K回应
        if len(request.data) == 4 * 1024:
            return data_4k
        else:
            return 'Invalid data size', 400
    elif test_type == '3':
        # 测试类型3：发送4K数据，无回应
        if len(request.data) == 4 * 1024:
            return '', 204
        else:
            return 'Invalid data size', 400
    elif test_type == '4':
        # 测试类型4：发送不含数据，接收4K回应
        return data_4k
    elif test_type == '5':
        # 测试类型5：发送150K数据，接收150K回应
        if len(request.data) == 150 * 1024:
            return data_150k
        else:
            return 'Invalid data size', 400
    elif test_type == '6':
        # 测试类型6：发送150K数据，无回应
        if len(request.data) == 150 * 1024:
            return '', 204
        else:
            return 'Invalid data size', 400
    elif test_type == '7':
        # 测试类型7：发送不含数据，接收150K回应
        return data_150k
    else:
        return 'Invalid test type', 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=11111)
