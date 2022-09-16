# encoding=utf-8
import argparse
import base64
import json
from io import BytesIO

import ddddocr
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, request

parser = argparse.ArgumentParser(description="使用ddddocr搭建的最简api服务")
parser.add_argument("-p", "--port", type=int, default=9898)
parser.add_argument("--ocr", action="store_true", help="开启ocr识别")
parser.add_argument("--old", action="store_true", help="OCR是否启动旧模型")
parser.add_argument("--det", action="store_true", help="开启目标检测")

args = parser.parse_args()

app = Flask(__name__)


class Server(object):

  def __init__(self, ocr=True, det=False, old=False):
    self.ocr_option = ocr
    self.det_option = det
    self.old_option = old
    self.ocr = None
    self.det = None
    if self.ocr_option:
      print("ocr模块开启")
      if self.old_option:
        print("使用OCR旧模型启动")
        self.ocr = ddddocr.DdddOcr(old=True, show_ad=False)
      else:
        print("使用OCR新模型启动，如需要使用旧模型，请额外添加参数  --old开启")
        self.ocr = ddddocr.DdddOcr(show_ad=False)
    else:
      print("ocr模块未开启，如需要使用，请使用参数  --ocr开启")
    if self.det_option:
      print("目标检测模块开启")
      self.det = ddddocr.DdddOcr(det=True, show_ad=False)
    else:
      print("目标检测模块未开启，如需要使用，请使用参数  --det开启")

  def classification(self, img: bytes):
    if self.ocr_option:
      return self.ocr.classification(img)
    else:
      raise Exception("ocr模块未开启")

  def draw(self, img, poses):
    # 字体
    font_type = "./msyhl.ttc"
    font_size = 20
    # 识别
    image = Image.open(BytesIO(img))
    draw = ImageDraw.Draw(image)
    words = []
    for row in poses:
      # 框字
      x1, y1, x2, y2 = row
      draw.line(([(x1, y1), (x1, y2), (x2, y2), (x2, y1), (x1, y1)]), width=1, fill="red")
      # 裁剪
      crop = image.crop(row)
      image_byte = BytesIO()
      crop.save(image_byte, 'png')
      word = self.ocr.classification(image_byte.getvalue())
      if word == '':
        word = str(len(words)) + '-'
      words.append(word)
      # 填字
      y = y1 - 30 if y2 > 300 else y2
      draw.text((int((x1 + x2) / 2), y), word, font=ImageFont.truetype(font_type, font_size), fill="red")
    #image.show()
    img_byte = BytesIO()
    image.save(img_byte, 'png')
    return (words, img_byte.getvalue())

  def detection(self, img: bytes, kind='word', crop_size=(0, 0, 344, 344)):
    if self.det_option:
      image = Image.open(BytesIO(img))
      # print(image.size)
      if crop_size:
        image = image.crop(crop_size)
        image_byte = BytesIO()
        image.save(image_byte, 'png')
        img = image_byte.getvalue()
      poses = self.det.detection(img)
      if kind == 'pose':
        return poses
      words, imgbytes = self.draw(img, poses)
      if kind == 'image':
        return base64.b64encode(imgbytes).decode('utf-8')
      wps = {}
      for key, pose in dict(zip(words, poses)).items():
        wps[key] = (int((pose[0] + pose[2]) / 2), int((pose[1] + pose[3]) / 2))
      return wps
    else:
      raise Exception("目标检测模块模块未开启")

  def slide(self, target_img: bytes, bg_img: bytes, algo_type: str):
    dddd = self.ocr or self.det or ddddocr.DdddOcr(ocr=False)
    if algo_type == 'match':
      return dddd.slide_match(target_img, bg_img)
    elif algo_type == 'compare':
      return dddd.slide_comparison(target_img, bg_img)
    else:
      raise Exception(f"不支持的滑块算法类型: {algo_type}")


server = Server(ocr=args.ocr, det=args.det, old=args.old)


def get_img(request, img_type='file', img_name='image'):
  if img_type == 'b64':
    img = base64.b64decode(request.get_data())  #
    try:  # json str of multiple images
      dic = json.loads(img)
      img = base64.b64decode(dic.get(img_name).encode())
    except Exception as e:  # just base64 of single image
      pass
  else:
    img = request.files.get(img_name).read()
  return img


def set_ret(result):
  if isinstance(result, Exception):
    return json.dumps({"status": 200, "result": "", "msg": str(result)}, ensure_ascii=False)
  else:
    return json.dumps({"status": 200, "result": result, "msg": ""}, ensure_ascii=False)


@app.route('/<opt>/<img_type>', methods=['POST'])
@app.route('/<opt>/<img_type>/<kind>', methods=['POST'])
def ocr(opt, img_type='file', kind='word'):
  try:
    img = get_img(request, img_type)
    if opt == 'ocr':
      result = server.classification(img)
    elif opt == 'det':
      result = server.detection(img, kind)
    else:
      raise f"<opt={opt}> is invalid"
    return set_ret(result)
  except Exception as e:
    return set_ret(e)


@app.route('/slide/<algo_type>/<img_type>', methods=['POST'])
def slide(algo_type='compare', img_type='file'):
  try:
    target_img = get_img(request, img_type, 'target_img')
    bg_img = get_img(request, img_type, 'bg_img')
    result = server.slide(target_img, bg_img, algo_type)
    return set_ret(result)
  except Exception as e:
    return set_ret(e)


@app.route('/ping', methods=['GET'])
def ping():
  return "pong"


if __name__ == '__main__':
  # with open(r'./test.png', 'rb') as f:
  #   img = f.read()
  #   bs = base64.b64encode(img).decode('utf-8')
  #   print(bs)

  app.run(host="0.0.0.0", port=args.port)
