import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

from pygame.locals import *
from random import *
import traceback
import pygame
import sys
import _plane
import plane
import shield
import enemy
import enemy_bullet
import bullet
import supply
import cv2
import numpy as np

from rockx import RockX
import math
import argparse

import sqlite3

from pose import estimate_head_pose

class FaceDB:

    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file)
        self.cursor = self.conn.cursor()
        if not self._is_face_table_exist():
            self.cursor.execute("create table FACE (NAME text, VERSION int, FEATURE blob, ALIGN_IMAGE blob)")

    def load_face(self):
        all_face = dict()
        c = self.cursor.execute("select * from FACE")
        for row in c:
            name = row[0]
            version = row[1]
            feature = np.frombuffer(row[2], dtype='float32')
            align_img = np.frombuffer(row[3], dtype='uint8')
            align_img = align_img.reshape((112, 112, 3))
            all_face[name] = {
                'feature': RockX.FaceFeature(version=version, len=feature.size, feature=feature),
                'image': align_img
            }
        return all_face

    def insert_face(self, name, feature, align_img):
        self.cursor.execute("INSERT INTO FACE (NAME, VERSION, FEATURE, ALIGN_IMAGE) VALUES (?, ?, ?, ?)",
                            (name, feature.version, feature.feature.tobytes(), align_img.tobytes()))
        self.conn.commit()

    def _get_tables(self):
        cursor = self.cursor
        cursor.execute("select name from sqlite_master where type='table' order by name")
        tables = cursor.fetchall()
        return tables

    def _is_face_table_exist(self):
        tables = self._get_tables()
        for table in tables:
            if 'FACE' in table:
                return True
        return False


def get_max_face(results):
    max_area = 0
    max_face = None
    for result in results:
        area = (result.box.bottom - result.box.top) * (result.box.right * result.box.left)
        if area > max_area:
            max_face = result
    return max_face


def get_face_feature(image_path):
    face_recog_handle = RockX(RockX.ROCKX_MODULE_FACE_RECOGNIZE, target_device=args.device)
    img = cv2.imread(image_path)
    img_h, img_w = img.shape[:2]
    ret, results = face_det_handle.rockx_face_detect(img, img_w, img_h, RockX.ROCKX_PIXEL_FORMAT_BGR888)
    if ret != RockX.ROCKX_RET_SUCCESS:
        return None, None
    max_face = get_max_face(results)
    if max_face is None:
        return None, None
    ret, align_img = face_landmark5_handle.rockx_face_align(img, img_w, img_h,
                                                            RockX.ROCKX_PIXEL_FORMAT_BGR888,
                                                            max_face.box, None)
    if ret != RockX.ROCKX_RET_SUCCESS:
        return None, None
    if align_img is not None:
        ret, face_feature = self.face_recog_handle.rockx_face_recognize(align_img)
        if ret == RockX.ROCKX_RET_SUCCESS:
            return face_feature, align_img
    return None, None


def get_all_image(image_path):
    img_files = dict()
    g = os.walk(image_path)

    for path, dir_list, file_list in g:
        for file_name in file_list:
            file_path = os.path.join(path, file_name)
            if not os.path.isdir(file_path):
                img_files[os.path.splitext(file_name)[0]] = file_path
    return img_files


def import_face(face_db, images_dir):
    image_files = get_all_image(images_dir)
    image_name_list = list(image_files.keys())
    for name, image_path in image_files.items():
        feature, align_img = get_face_feature(image_path)
        if feature is not None:
            face_db.insert_face(name, feature, align_img)
            print('[%d/%d] success import %s ' % (image_name_list.index(name)+1, len(image_name_list), image_path))
        else:
            print('[%d/%d] fail import %s' % (image_name_list.index(name)+1, len(image_name_list), image_path))


def search_face(face_library, cur_feature):
    face_recog_handle = RockX(RockX.ROCKX_MODULE_FACE_RECOGNIZE, target_device=args.device)
    min_similarity = 10.0
    target_name = None
    target_face = None
    for name, face in face_library.items():
        feature = face['feature']
        ret, similarity = face_recog_handle.rockx_face_similarity(cur_feature, feature)
        if similarity < min_similarity:
            target_name = name
            min_similarity = similarity
            target_face = face
    if min_similarity < 1.0:
        return target_name, min_similarity, target_face
    return None, -1, None




class HeadPostEstimation():
    """
    头部姿态识别
    """

    def __init__(self):
        parser = argparse.ArgumentParser(description="face controlled game")
        parser.add_argument('-c', '--camera', help="camera index", type=int, default=10)
        parser.add_argument('-d', '--device', help="target device id", type=str)
        #parser.add_argument('-b', '--db_file', help="face database path", required=True)
        parser.add_argument('-b', '--db_file', help="face database path", default="face.db")
        parser.add_argument('-i', '--image_dir', help="import image dir")
        self.args = parser.parse_args()

        #self.face_det_handle = RockX(RockX.ROCKX_MODULE_FACE_DETECTION, target_device=self.args.device)
        #self.face_landmark68_handle = RockX(RockX.ROCKX_MODULE_FACE_LANDMARK_68, target_device=self.args.device)
        #self.face_landmark5_handle = RockX(RockX.ROCKX_MODULE_FACE_LANDMARK_5, target_device=self.args.device)
        #self.face_recog_handle = RockX(RockX.ROCKX_MODULE_FACE_RECOGNIZE, target_device=self.args.device)
        #self.face_track_handle = RockX(RockX.ROCKX_MODULE_OBJECT_TRACK, target_device=self.args.device)
        
        self.face_db = FaceDB(self.args.db_file)
        
        if self.args.image_dir is not None:
            import_face(self.face_db, self.args.image_dir)
            exit(0)
        
        # load face from database
        self.face_library = self.face_db.load_face()
        print("load %d face" % len(self.face_library))
        
        self.flag = 0;
        #self.m_time = 0;
        #face_landmark5_handle = RockX(RockX.ROCKX_MODULE_FACE_LANDMARK_5, target_device=args.device)
        #face_attr_handle = RockX(RockX.ROCKX_MODULE_FACE_ANALYZE, target_device=args.device)

    def classify_pose(self, video):
        """
        video 表示不断产生图片的生成器
        """
        #return 0, 0, 0
        
        ret_p = 0
        ret_y = 0
        ret_r = 0  
        img = video
        #for index, img in enumerate(video(), start=1):
        #self.img_size = img.shape
        
        #print(index)

        frame = img
        show_frame = img
        in_img_h, in_img_w = img.shape[:2]
        ret, results = face_det_handle.rockx_face_detect(frame, in_img_w, in_img_h, RockX.ROCKX_PIXEL_FORMAT_BGR888)
        
        #ret, results = face_track_handle.rockx_object_track(in_img_w, in_img_h, 3, results)

        #self.m_time = self.m_time + 1
        #if self.m_time == 20:
        #    self.m_time = 0
        index = 0
        for result in results:
        
            key_pressed = pygame.key.get_pressed()
            if key_pressed[K_c]:
                print("get check")
            # face align
                ret, align_img = face_landmark5_handle.rockx_face_align(frame, in_img_w, in_img_h,
                                                                 RockX.ROCKX_PIXEL_FORMAT_BGR888,
                                                                 result.box, None)
            
            # get face feature
                if ret == RockX.ROCKX_RET_SUCCESS and align_img is not None:
                    ret, face_feature = face_recog_handle.rockx_face_recognize(align_img)
            
            # search face
                if ret == RockX.ROCKX_RET_SUCCESS and face_feature is not None:
                    target_name, diff, target_face = search_face(self.face_library, face_feature)
                    print("target_name=%s diff=%s", target_name, str(diff))
                self.flag = 0
                if ret == RockX.ROCKX_RET_SUCCESS and face_feature is not None and target_name == "YCZ":
                    self.flag = 1
                    print("get flag")
           
       
        # face landmark

            ret, landmark = face_landmark68_handle.rockx_face_landmark(frame, in_img_w, in_img_h,
                                                                   RockX.ROCKX_PIXEL_FORMAT_BGR888,
                                                                   result.box)
            #print(landmark)

        # face pose
            ret, face_angle = face_landmark68_handle.rockx_face_pose(landmark)

            #euler_angle_lst, directions_lst, landmarks_lst = estimate_head_pose(landmark.landmarks, True)

        # draw
        #    cv2.rectangle(show_frame,
        #              (result.box.left, result.box.top),
        #              (result.box.right, result.box.bottom),
        #              (0, 255, 0), 2)

            if face_angle is not None and landmark.landmarks_count > 0 and self.flag > 0:
                print('face angle: %f %f %f' % (face_angle.pitch, face_angle.yaw, face_angle.roll))
                cv2.putText(show_frame, "p=%.0f y=%.0f r=%.0f" % (face_angle.pitch, face_angle.yaw, face_angle.roll), (result.box.left, result.box.bottom+30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0))
                ret_p = face_angle.pitch
                ret_y = face_angle.yaw
                ret_r = face_angle.roll
            for p in landmark.landmarks:
                cv2.circle(show_frame, (p.x, p.y), 1, (0, 255, 0), 2)
            index += 1
        cv2.imshow('face_analyze - '+str(self.args.device),show_frame)

        return ret_p, ret_y, ret_r


pygame.init()
pygame.mixer.init()

background_colour = (210, 210, 220)
RED = (255, 0, 0)
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 64)
min = 0
modes = pygame.display.list_modes()
# size = width, height = modes[min][0]//2 - 100, modes[min][1]-100
size = width, height = 512, 758
screen = pygame.display.set_mode(size)
pygame.display.set_caption("飞机大战v1.0")


def add_small_enemies(group1, group2, num):
    for i in range(num):
        smallenemy = enemy.SmallEnemy(size)
        group1.add(smallenemy)
        group2.add(smallenemy)


def add_mid_enemies(group1, group2, num):
    for i in range(num):
        midenemy = enemy.MidEnemy(size)
        group1.add(midenemy)
        group2.add(midenemy)


def add_big_enemies(group1, group2, num):
    for i in range(num):
        bigenemy = enemy.BigEnemy(size)
        group1.add(bigenemy)
        group2.add(bigenemy)


def inc_speed(target, inc):
    for each in target:
        each.speed += inc


def main():



    # 加载音乐
    #pygame.mixer.music.load("sound/game_music.wav")
    #pygame.mixer.music.set_volume(0.2)
    #pygame.mixer.music.play(-1)# 参数-1表示无限循环音乐

    enemy3_flying = pygame.mixer.Sound("sound/enemy3_flying.wav")
    enemy3_flying.set_volume(0.1)

    enemy3_down = pygame.mixer.Sound("sound/enemy3_down.wav")
    enemy3_down.set_volume(0.3)
    enemy2_down = pygame.mixer.Sound("sound/enemy2_down.wav")
    enemy2_down.set_volume(0.1)
    enemy1_down = pygame.mixer.Sound("sound/enemy1_down.wav")
    enemy1_down.set_volume(0.1)
    my_down = pygame.mixer.Sound("sound/me_down.wav")
    my_down.set_volume(0.1)
    bullet_sound = pygame.mixer.Sound("sound/bullet.wav")
    bullet_sound.set_volume(0.2)
    bomb_sound_use = pygame.mixer.Sound("sound/use_bomb.wav")
    bomb_sound_use.set_volume(0.3)
    upgrade_sound = pygame.mixer.Sound("sound/upgrade.wav")
    upgrade_sound.set_volume(0.4)
    supply_sound = pygame.mixer.Sound("sound/supply.wav")
    supply_sound.set_volume(0.4)


    #背景图片
    bg_image1 = pygame.image.load("bgimages/bg1.jpg")
    bg_image2 = pygame.image.load("bgimages/bg2.jpg")
    bg_image3 = pygame.image.load("bgimages/bg3.jpg")
    bg_image4 = pygame.image.load("bgimages/bg4.jpg")
    bg_image5 = pygame.image.load("bgimages/bg5.jpg")

    bg = bg_image1

    # 得分
    score = 0
    score_font = pygame.font.Font("font/BrushScriptStd.ttf", 36)
    score_font1 = pygame.font.Font("font/BrushScriptStd.ttf", 24)
    score_font2 = pygame.font.Font("font/msyh.ttf", 18)

    # 存档判断
    opened = False

    # 默认难度
    lv = 1
    lv_dict = {1: 4, 2: 3, 3: 3, 4: 2, 5: 1}

    # 是否祝贺
    is_congratulate = False

    # 是否切换难度
    transform = True

    # 是否激光扫屏
    sweep = False

    prize_life_num = 0
    prize_bomb_num = 0

    # 暂停图片
    paused = False
    pause_nor_image = pygame.image.load("images/pause_nor.png").convert_alpha()
    pause_pressed_image = pygame.image.load("images/pause_pressed.png").convert_alpha()
    resume_nor_image = pygame.image.load("images/resume_nor.png").convert_alpha()
    resume_pressed_image = pygame.image.load("images/resume_pressed.png").convert_alpha()
    pause_rect = pause_nor_image.get_rect()
    pause_rect.left, pause_rect.top = size[0] - pause_rect.width - 20, 20
    pause_image = pause_nor_image

    # 结束界面
    stop_image = pygame.image.load("images/gameover.png").convert_alpha()
    stop_rect = stop_image.get_rect()
    stop_rect.left, stop_rect.top = (size[0] - stop_rect.width) // 2, \
                                    (size[1] - stop_rect.height) // 2 + 250
    restart_image = pygame.image.load("images/again.png").convert_alpha()
    restart_rect = restart_image.get_rect()
    restart_rect.left, restart_rect.top = (size[0] - stop_rect.width) // 2, \
                                          (size[1] - stop_rect.height) // 2 + 150

    # 索引子弹击中敌人图片
    small_destroy_index = 0
    mid_destroy_index = 0
    big_destroy_index = 0
    my_destroy_index = 0
    life_index = 0

    # 生成我方飞机
    myplane = plane.Plane(size)

    # 生成防护罩(shield)
    shields = shield.Shield()

    # 我方生命数量
    life_num = 8
    life_image = pygame.image.load("images/life.png").convert_alpha()
    life_rect = life_image.get_rect()

    # 自带炸弹
    bomb_image = pygame.image.load("images/bomb.png").convert_alpha()
    bomb_rect = bomb_image.get_rect()
    bomb_rect.left, bomb_rect.top = 10, size[1] - bomb_rect.height - 10
    bomb_num = 10
    bomb_font = pygame.font.Font("font/font.ttf", 35)

    # 补给定时
    supply_bomb = supply.Bomb(size)
    supply_bullet = supply.Bullet(size)

    SUPPLY_TIME = USEREVENT
    pygame.time.set_timer(SUPPLY_TIME, 25 * 1000)

    # ==========================================================
    enemies = pygame.sprite.Group()
    # 生成小型敌机
    smallenemies = pygame.sprite.Group()
    add_small_enemies(smallenemies, enemies, 14)

    # 生成中型敌机
    midenemies = pygame.sprite.Group()
    add_mid_enemies(midenemies, enemies, 4)

    # 生成大型敌机
    bigenemies = pygame.sprite.Group()
    add_big_enemies(bigenemies, enemies, 2)

    # 生成boss
    bosses = pygame.sprite.Group()
    boss = enemy.Boss(size)
    enemies.add(boss)
    bosses.add(boss)
    # ==========================================================

    # 敌机毁灭时奖励补给
    _prize_bomb = pygame.sprite.Group()
    _prize_bullet = pygame.sprite.Group()
    _prize_life = pygame.sprite.Group()

    # 敌机boss毁灭时奖励
    _prize_boss = pygame.sprite.Group()

    # 加强子弹定时器
    DOUBLE_BULLET_TIME = USEREVENT + 1
    # 标志是否使用加强子弹
    is_double = False

    # 无敌计时器
    INVINCIBLE_TIME = USEREVENT + 2

    # 生成我方扫屏激光
    my_lasers = []
    my_lasers_index = 0
    MY_LASERS_NUM = 1
    for i in range(MY_LASERS_NUM):
        my_lasers.append(bullet.My_lasers())

    # 激光1(直)
    lasers1 = []
    lasers1_index = 0
    LASERS1_NUM = 2
    for i in range(LASERS1_NUM // 2):
        lasers1.append(enemy_bullet.Lasers1(size, (boss.rect.centerx - 65, boss.rect.centery)))
        lasers1.append(enemy_bullet.Lasers1(size, (boss.rect.centerx + 65, boss.rect.centery)))

    # 子弹1
    bullet1 = []
    bullet1_index = 0
    BULLET1_NUM = 5
    for i in range(BULLET1_NUM):
        bullet1.append(bullet.Bullet1(myplane.rect.midtop))
    # 子弹2
    bullet2 = []
    bullet2_index = 0
    BULLET2_NUM = 12
    for i in range(BULLET2_NUM // 2):
        bullet2.append(bullet.Bullet2((myplane.rect.centerx - 33, myplane.rect.centery)))
        bullet2.append(bullet.Bullet2((myplane.rect.centerx + 30, myplane.rect.centery)))
    # 子弹3
    bullet3 = []
    bullet3_index = 0
    BULLET3_NUM = 18
    for i in range(BULLET3_NUM // 3):
        bullet3.append(bullet.Bullet2((myplane.rect.centerx - 33, myplane.rect.centery)))
        bullet3.append(bullet.Bullet1(myplane.rect.midtop))
        bullet3.append(bullet.Bullet2((myplane.rect.centerx + 30, myplane.rect.centery)))
    # 子弹4
    bullet4 = []
    bullet4_index = 0
    BULLET4_NUM = 24
    for i in range(BULLET4_NUM // 4):
        bullet4.append(bullet.Bullet1((myplane.rect.centerx - 33, myplane.rect.centery)))
        bullet4.append(bullet.Bullet2((myplane.rect.centerx - 15, myplane.rect.centery)))
        bullet4.append(bullet.Bullet2((myplane.rect.centerx + 15, myplane.rect.centery)))
        bullet4.append(bullet.Bullet1((myplane.rect.centerx + 30, myplane.rect.centery)))
    # 子弹5
    bullet5 = []
    bullet5_index = 0
    BULLET5_NUM = 30
    for i in range(BULLET5_NUM // 5):
        bullet5.append(bullet.Bullet4((myplane.rect.centerx - 33, myplane.rect.centery)))
        bullet5.append(bullet.Bullet3((myplane.rect.centerx - 15, myplane.rect.centery)))
        bullet5.append(bullet.Bullet2(myplane.rect.midtop))
        bullet5.append(bullet.Bullet3((myplane.rect.centerx + 15, myplane.rect.centery)))
        bullet5.append(bullet.Bullet4((myplane.rect.centerx + 30, myplane.rect.centery)))
    # 子弹6
    bullet6 = []
    bullet6_index = 0
    BULLET6_NUM = 36
    for i in range(BULLET6_NUM // 6):
        bullet6.append(bullet.Bullet1((myplane.rect.centerx - 33, myplane.rect.centery)))
        bullet6.append(bullet.Bullet2((myplane.rect.centerx - 22, myplane.rect.centery)))
        bullet6.append(bullet.Bullet3((myplane.rect.centerx - 10, myplane.rect.centery)))
        bullet6.append(bullet.Bullet3((myplane.rect.centerx + 10, myplane.rect.centery)))
        bullet6.append(bullet.Bullet2((myplane.rect.centerx + 22, myplane.rect.centery)))
        bullet6.append(bullet.Bullet1((myplane.rect.centerx + 30, myplane.rect.centery)))

    # 子弹7
    bullet7 = []
    bullet7_index = 0
    BULLET7_NUM = 42
    for i in range(BULLET7_NUM // 7):
        bullet7.append(bullet.Bullet4((myplane.rect.centerx - 33, myplane.rect.centery)))
        bullet7.append(bullet.Bullet1((myplane.rect.centerx - 22, myplane.rect.centery)))
        bullet7.append(bullet.Bullet2((myplane.rect.centerx - 10, myplane.rect.centery)))
        bullet7.append(bullet.Bullet3(myplane.rect.midtop))
        bullet7.append(bullet.Bullet3((myplane.rect.centerx + 10, myplane.rect.centery)))
        bullet7.append(bullet.Bullet1((myplane.rect.centerx + 22, myplane.rect.centery)))
        bullet7.append(bullet.Bullet4((myplane.rect.centerx + 30, myplane.rect.centery)))
    # 子弹8
    bullet8 = []
    bullet8_index = 0
    BULLET8_NUM = 48
    for i in range(BULLET8_NUM // 8):
        bullet8.append(bullet.Bullet4((myplane.rect.centerx - 45, myplane.rect.centery)))
        bullet8.append(bullet.Bullet1((myplane.rect.centerx - 35, myplane.rect.centery)))
        bullet8.append(bullet.Bullet2((myplane.rect.centerx - 24, myplane.rect.centery)))
        bullet8.append(bullet.Bullet3((myplane.rect.centerx - 10, myplane.rect.centery)))
        bullet8.append(bullet.Bullet3((myplane.rect.centerx + 10, myplane.rect.centery)))
        bullet8.append(bullet.Bullet2((myplane.rect.centerx + 22, myplane.rect.centery)))
        bullet8.append(bullet.Bullet1((myplane.rect.centerx + 30, myplane.rect.centery)))
        bullet8.append(bullet.Bullet4((myplane.rect.centerx + 41, myplane.rect.centery)))
        # 子弹9
    bullet9 = []
    bullet9_index = 0
    BULLET9_NUM = 54
    for i in range(BULLET9_NUM // 9):
        bullet9.append(bullet.Bullet1((myplane.rect.centerx - 43, myplane.rect.centery)))
        bullet9.append(bullet.Bullet2((myplane.rect.centerx - 35, myplane.rect.centery)))
        bullet9.append(bullet.Bullet2((myplane.rect.centerx - 24, myplane.rect.centery)))
        bullet9.append(bullet.Bullet3((myplane.rect.centerx - 10, myplane.rect.centery)))
        bullet9.append(bullet.Bullet3(myplane.rect.midtop))
        bullet9.append(bullet.Bullet3((myplane.rect.centerx + 10, myplane.rect.centery)))
        bullet9.append(bullet.Bullet2((myplane.rect.centerx + 21, myplane.rect.centery)))
        bullet9.append(bullet.Bullet2((myplane.rect.centerx + 32, myplane.rect.centery)))
        bullet9.append(bullet.Bullet1((myplane.rect.centerx + 41, myplane.rect.centery)))
    # 子弹0
    bullet0 = []
    bullet0_index = 0
    BULLET0_NUM = 66
    for i in range(BULLET0_NUM // 11):
        bullet0.append(bullet.Bullet4((myplane.rect.centerx - 55, myplane.rect.centery)))
        bullet0.append(bullet.Bullet1((myplane.rect.centerx - 44, myplane.rect.centery)))
        bullet0.append(bullet.Bullet2((myplane.rect.centerx - 34, myplane.rect.centery)))
        bullet0.append(bullet.Bullet2((myplane.rect.centerx - 23, myplane.rect.centery)))
        bullet0.append(bullet.Bullet3((myplane.rect.centerx - 10, myplane.rect.centery)))
        bullet0.append(bullet.Bullet3(myplane.rect.midtop))
        bullet0.append(bullet.Bullet3((myplane.rect.centerx + 10, myplane.rect.centery)))
        bullet0.append(bullet.Bullet2((myplane.rect.centerx + 21, myplane.rect.centery)))
        bullet0.append(bullet.Bullet2((myplane.rect.centerx + 30, myplane.rect.centery)))
        bullet0.append(bullet.Bullet1((myplane.rect.centerx + 41, myplane.rect.centery)))
        bullet0.append(bullet.Bullet4((myplane.rect.centerx + 50, myplane.rect.centery)))

    # 飞弹
    feidan = []
    feidan_index = 0
    FEIDAN_NUM = 12
    for i in range(FEIDAN_NUM // 2):
        feidan.append(bullet.Bullet5((myplane.rect.centerx - 55, myplane.rect.centery)))
        feidan.append(bullet.Bullet5((myplane.rect.centerx + 50, myplane.rect.centery)))

    # boss尾气
    boss_bullet = []
    boss_bullet_index = 0
    BOSS_BULLET_NUM = 2
    for i in range(BOSS_BULLET_NUM // 2):
        boss_bullet.append(enemy_bullet.Bullet(size))
        boss_bullet.append(enemy_bullet.Bullet(size))
    # ==========================================================
    boss_bullets = []
    # boss子弹1
    boss_bullet1 = []
    boss_bullet1_index = 0
    BOSS_BULLET1_NUM = 4
    for i in range(BOSS_BULLET1_NUM // 4):
        boss_bullet1.append(enemy_bullet.Bullet_a(size))
        boss_bullet1.append(enemy_bullet.Bullet1(size))
        boss_bullet1.append(enemy_bullet.Bullet1(size))
        boss_bullet1.append(enemy_bullet.Bullet_a(size))

    # boss子弹2
    boss_bullet2 = []
    boss_bullet2_index = 0
    BOSS_BULLET2_NUM = 4
    for i in range(BOSS_BULLET2_NUM // 4):
        boss_bullet2.append(enemy_bullet.Bullet_a(size))
        boss_bullet2.append(enemy_bullet.Bullet2(size))
        boss_bullet2.append(enemy_bullet.Bullet2(size))
        boss_bullet2.append(enemy_bullet.Bullet_a(size))

    # boss子弹3
    boss_bullet3 = []
    boss_bullet3_index = 0
    BOSS_BULLET3_NUM = 4
    for i in range(BOSS_BULLET3_NUM // 4):
        boss_bullet3.append(enemy_bullet.Bullet_a(size))
        boss_bullet3.append(enemy_bullet.Bullet3(size))
        boss_bullet3.append(enemy_bullet.Bullet3(size))
        boss_bullet3.append(enemy_bullet.Bullet_a(size))

    # 用于切换图片
    switch_image = True
    # 用于延迟帧率
    delay = 10
    # 用于计boss能量
    _delay = 0

    # 用于计算我方mp
    # m为随着等级提升而增加的能量上限
    m = 1000
    mp = m // 20

    # 暂停敌机移动
    is_move = True

    running = True

    # 使用头部控制飞机
    #face_detector = MyFaceDetector()
    # 打开摄像头

    cap = cv2.VideoCapture(10)
    cap.set(3, 1280)
    cap.set(4, 720)
    last_face_feature = None

    def generate_image():
        while True:
            # frame_rgb即视频的一帧数据
            ret, frame_rgb = cap.read()
            # 按q键即可退出
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            if frame_rgb is None:
                break
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            #yield frame_bgr
            return frame_bgr
        #cap.release()
        #cv2.destroyAllWindows()

    head_post = HeadPostEstimation()
    head_angle_yaw_ref = 0
    head_angle_pitch_ref = 0

    imindex = 0
    #inc_speed(smallenemies,2)
    while running:
        #screen.fill(background_colour)

        screen.blit(bg,(0,0))
        # 事件循环
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()

            elif life_num >= 0:
                if event.type == MOUSEBUTTONDOWN:
                    if event.button == 1 and pause_rect.collidepoint(event.pos):
                        paused = not paused
                        if paused:
                            #pygame.mixer.music.pause()
                            pygame.mixer.pause()
                        else:
                            #pygame.mixer.music.unpause()
                            pygame.mixer.unpause()

                elif event.type == MOUSEMOTION:
                    if pause_rect.collidepoint(event.pos):
                        if paused:
                            pause_image = resume_pressed_image
                        else:
                            pause_image = pause_pressed_image
                    else:
                        if paused:
                            pause_image = resume_nor_image
                        else:
                            pause_image = pause_nor_image

                elif not paused and event.type == KEYDOWN:
                    if bomb_num and event.key == K_SPACE:
                        bomb_sound_use.play()
                        bomb_num -= 1
                        if mp < m - m // 20:
                            mp += m // 20
                        else:
                            mp = m

                        for each in enemies:
                            if each in bosses:
                                if each.rect.bottom == each.rect.height:
                                    each.energy -= 50
                                    if each.energy <= 0:
                                        each.active = False
                            else:
                                if each.rect.bottom > 0:
                                    each.active = False
                        if bomb_num <= 0:
                            bomb_num = 0

                elif event.type == SUPPLY_TIME:
                    if choice([True, False]):
                        supply_bomb.reset()
                    else:
                        supply_bullet.reset()

                elif event.type == DOUBLE_BULLET_TIME:
                    is_double = False
                    pygame.time.set_timer(DOUBLE_BULLET_TIME, 0)

                elif event.type == INVINCIBLE_TIME:
                    myplane.invincible = False
                    myplane.blink = False
                    pygame.time.set_timer(INVINCIBLE_TIME, 0)

            elif event.type == MOUSEBUTTONDOWN:
                if event.button == 1 and stop_rect.collidepoint(event.pos):
                    pygame.quit()
                    sys.exit()

                elif event.button == 1 and restart_rect.collidepoint(event.pos):
                    cap.release()
                    cv2.destroyAllWindows()
                    main()
        
        
        # 难度设置
        if lv == 1 and score > 500:
            if transform:
                # 增加2架小型敌机,1架中型敌机,1架大型敌机
                add_small_enemies(smallenemies, enemies, 3)
                add_mid_enemies(midenemies, enemies, 2)
                add_big_enemies(bigenemies, enemies, 1)
                # 增加小型敌机速度
                inc_speed(smallenemies,1)
                #inc_speed(smallenemies, 3)
                transform = False
                # 去掉所有其他敌机
                is_move = False
                boss.reset()

            if not boss.active:
                upgrade_sound.play()
                lv = 2
                is_move = True

                # 复位到原地等待reset()
                boss._return()
                transform = True
                score += 200
                bg = bg_image2
                shields.active = False
                myplane.invincible = False
                m += 200
                mp = m // 20

        elif lv == 2 and score > 1500:
            if transform:
                add_small_enemies(smallenemies, enemies, 2)
                add_mid_enemies(midenemies, enemies, 2)
                add_big_enemies(bigenemies, enemies, 1)
                # 增加小型敌机速度
                inc_speed(smallenemies, 1)
                inc_speed(midenemies, 1)
                inc_speed(bigenemies, 1)
                transform = False

                is_move = False
                boss.reset()

            if not boss.active:
                upgrade_sound.play()
                lv = 3
                is_move = True
                boss._return()
                transform = True
                score += 500
                bg = bg_image3
                enemy.BigEnemy.energy += 10
                shields.active = False
                myplane.invincible = False
                m += 500
                mp = m // 20

        elif lv == 3 and score > 4500:
            if transform:
                # 增加3架小型敌机,2架中型敌机,1架大型敌机
                add_small_enemies(smallenemies, enemies, 2)
                add_mid_enemies(midenemies, enemies, 2)
                add_big_enemies(bigenemies, enemies, 1)
                # 增加小型敌机速度
                inc_speed(smallenemies, 2)
                inc_speed(midenemies, 1)
                transform = False

                is_move = False
                boss.reset()

            if not boss.active:
                upgrade_sound.play()
                lv = 4
                is_move = True
                boss._return()
                transform = True
                score += 800
                bg = bg_image4
                enemy.MidEnemy.energy += 5
                enemy.BigEnemy.energy += 10
                shields.active = False
                myplane.invincible = False
                m += 1000
                mp = m // 20

        elif lv == 4 and score > 13500:
            if transform:
                # 增加4架小型敌机,2架中型敌机,1架大型敌机
                add_small_enemies(smallenemies, enemies, 2)
                add_mid_enemies(midenemies, enemies, 2)
                add_big_enemies(bigenemies, enemies, 1)
                # 增加小型敌机速度
                inc_speed(smallenemies, 2)
                inc_speed(midenemies, 1)
                inc_speed(bigenemies, 1)
                transform = False

                is_move = False
                boss.reset()

            if not boss.active:
                upgrade_sound.play()
                lv = 5
                is_move = True
                boss._return()
                transform = True
                score += 1100
                bg = bg_image5
                enemy.MidEnemy.energy += 5
                enemy.BigEnemy.energy += 10
                shields.active = False
                myplane.invincible = False
                m += 2000
                mp = m // 20

        elif lv == 5 and score > 40500:
            if transform:
                add_mid_enemies(midenemies, enemies, 5)
                add_big_enemies(bigenemies, enemies, 3)
                for each in smallenemies:
                    each.speed = 1
                enemy.BigEnemy.energy = 220
                enemy.MidEnemy.energy = 50
                # 减少敌机速度
                inc_speed(midenemies, -2)
                inc_speed(bigenemies, -2)
                transform = False

                is_move = False
                boss.reset()

            if not boss.active:
                upgrade_sound.play()
                lv = 6
                is_move = True
                boss._return()
                transform = True
                score += 1400
                # bg = bg_image6
                shields.active = False
                myplane.invincible = False
                m += 3000
                mp = m // 20

        elif lv == 6 and score > 1000000:
            if transform:
                for each in smallenemies:
                    each.speed = 8

                enemy.BigEnemy.energy -= 20
                enemy.MidEnemy.energy -= 100
                add_small_enemies(smallenemies, enemies, 2)
                add_mid_enemies(midenemies, enemies, 1)
                inc_speed(midenemies, 3)
                inc_speed(bigenemies, 3)
                transform = False
                is_move = False
                boss.reset()

            if not boss.active:
                upgrade_sound.play()
                is_move = True
                boss._return()
                transform = True
                score += 10000
                # bg = bg_image6
                shields.active = False
                myplane.invincible = False
                m += 5000
                mp = m // 20

        # 更新分数
        score_text = score_font.render("Score:%s" % str(score), True, RED)
        screen.blit(score_text, (15, 8))
        # 更新关卡
        level_text = score_font1.render("Level:%s" % str(lv), True, RED)
        screen.blit(level_text, (15, 45))
        # 更新暂停按钮
        screen.blit(pause_image, pause_rect)

        clock = pygame.time.Clock()

        if not paused and life_num >= 0:
            # 绘制我方飞机数量
            for i in range(life_num):
                life_rect.left, life_rect.top = size[0] - (i + 1) * life_rect.width, \
                                                size[1] - life_rect.height - 10
                screen.blit(life_image, life_rect)

            # 更新炸弹数量
            bomb_text = bomb_font.render("×%s" % str(bomb_num), True, BLACK)
            screen.blit(bomb_text, (75, size[1] - bomb_rect.height + 2))
            # 生成炸弹
            screen.blit(bomb_image, bomb_rect)

            
            #获取键盘事件
            key_pressed = pygame.key.get_pressed()
            if key_pressed[K_w] or key_pressed[K_UP]:
                myplane.move_up()
            elif key_pressed[K_s] or key_pressed[K_DOWN]:
                myplane.move_down()
            elif key_pressed[K_a] or key_pressed[K_LEFT]:
                myplane.move_left()
            elif key_pressed[K_d] or key_pressed[K_RIGHT]:
                myplane.move_right()
            #启动我方飞机防护罩
            elif key_pressed[K_RETURN]:
                if _mp_remain == 1:
                    shields.reset()
                    mp = 50
            elif key_pressed[K_x]:
                 cap.release()
                 cv2.destroyAllWindows()
                 
                 main()
            

            head_angle_pitch=0
            head_angle_yaw=0
            head_angle_roll=0
            imindex+=1
            #获取角度
            if imindex == 2: 
                img = generate_image()
                #print(img)
                head_angle_pitch, head_angle_yaw, head_angle_roll = head_post.classify_pose(video=img)
                imindex = 0
            #获取键盘事件
            key_pressed = pygame.key.get_pressed()
            #更新头部初始角度
            if key_pressed[K_r]:
                head_angle_pitch_ref = head_angle_pitch;
                head_angle_yaw_ref = head_angle_yaw;
            
            
            if head_angle_yaw < head_angle_yaw_ref-2 and head_angle_yaw != 0:
                myplane.move_left() # 由于摄像头演示中镜面关系，实际使用中请设置为myplane.move_right()
            elif head_angle_yaw > head_angle_yaw_ref+2 and head_angle_yaw != 0:
                myplane.move_right() # 由于摄像头演示中镜面关系，实际使用中请设置为myplane.move_left()
            elif head_angle_pitch < head_angle_pitch_ref-1 and head_angle_pitch != 0:
                myplane.move_up()
            elif head_angle_pitch > head_angle_pitch_ref+1 and head_angle_pitch != 0:
                myplane.move_down()
            
            
            lips_distance = 0
            
            # 张嘴就是炸弹，dis_control<0.045 为闭嘴
            if lips_distance < 0.045:
                flag = 1
            
            
            
            
            if bomb_num and lips_distance > 0.055 and flag == 1:
                flag = 0
                bomb_sound_use.play()
                bomb_num -= 1
                if mp < m - m // 20:
                    mp += m // 20
                else:
                    mp = m

                for each in enemies:
                    if each in bosses:
                        if each.rect.bottom == each.rect.height:
                            each.energy -= 50
                            if each.energy <= 0:
                                each.active = False
                    else:
                        if each.rect.bottom > 0:
                            each.active = False
                if bomb_num <= 0:
                    bomb_num = 0
        
            
            # 更新我方飞机
            if not myplane.blink:
                if not (delay % 5):
                    switch_image = not switch_image

                if myplane.active:
                    if switch_image:
                        screen.blit(myplane.image1, myplane.rect)
                    else:
                        screen.blit(myplane.image2, myplane.rect)
                else:
                    # 游戏结束
                    if not (delay % 3):
                        if my_destroy_index == 0:
                            my_down.play()
                        screen.blit(myplane.destroy_image[my_destroy_index], myplane.rect)
                        my_destroy_index = (my_destroy_index + 1) % 4
            else:
                # 说明发生碰撞但active非False
                # 复活时候闪烁
                if not (delay % 30):
                    switch_image = not switch_image
                if switch_image:
                    screen.blit(myplane.image1, myplane.rect)
                else:
                    screen.blit(myplane.destroy_image[-1], myplane.rect)

            # 更新能量mp
            _mp_remain = mp / m
            if _mp_remain == 1:
                mp_colour = GREEN
            else:
                mp_colour = YELLOW

            pygame.draw.line(screen, mp_colour, (45, size[1] - 80), (45 + 60 * _mp_remain, size[1] - 80), 15)

            e_text = score_font1.render("mp: ", True, BLACK)
            screen.blit(e_text, (8, size[1] - 90))

            # 更新我方飞机防护罩（shield）
            if shields.active:
                myplane.invincible = True
                shields.move((myplane.rect.left - 26, myplane.rect.top - 6))
                # 被激光击中时候闪烁图片
                if shields.hit:
                    if switch_image:
                        screen.blit(shields.image2, shields.rect)
                    else:
                        screen.blit(shields.image1, shields.rect)
                    shields.hit = False

                else:
                    screen.blit(shields.image1, shields.rect)

                # 碰撞检测（与子弹）
                shields_hit = pygame.sprite.spritecollide(shields, boss_bullets, False, pygame.sprite.collide_mask)
                if shields_hit:
                    for e in shields_hit:
                        e.active = False

                    shields.energy -= 1
                    if shields.energy <= 0:
                        shields.active = False
                        pygame.time.set_timer(INVINCIBLE_TIME, 3 * 1000)
                # 碰撞检测（与敌机）
                shields_hit1 = pygame.sprite.spritecollide(shields, enemies, False, pygame.sprite.collide_mask)
                if shields_hit1:
                    for u in shields_hit1:
                        if u in bosses:
                            u.energy *= 0.8
                            shields.energy = 0
                        elif u in bigenemies:
                            u.active = False
                            shields.energy -= 100 * lv
                        elif u in midenemies:
                            u.active = False
                            shields.energy -= 50 * lv
                        else:
                            u.active = False
                            shields.energy -= 10 * lv
                    if shields.energy <= 0:
                        shields.active = False
                        pygame.time.set_timer(INVINCIBLE_TIME, 3 * 1000)

                # 绘制防护罩血槽
                # pygame.draw.line(screen,background_colour,(45,size[1] - 110), (105, size[1] - 110), 15)
                _remain = shields.energy / shield.Shield.energy
                # 能量小于20%显示红色,其他绿色
                if _remain <= 0.2:
                    colour = YELLOW
                else:
                    colour = RED
                pygame.draw.line(screen, colour, (45, size[1] - 110), (45 + 60 * _remain, size[1] - 110), 15)

                e_text = score_font1.render("hp: ", True, BLACK)
                screen.blit(e_text, (10, size[1] - 120))

            # 加载飞弹
            if not (delay % 100):
                if isinstance(lv, int):
                    if lv >= 2 and is_double:
                        feidan[feidan_index + 0].reset((myplane.rect.centerx - 66, myplane.rect.centery))
                        feidan[feidan_index + 1].reset((myplane.rect.centerx + 48, myplane.rect.centery))
                        feidan_index = (feidan_index + 2) % FEIDAN_NUM
                else:
                    feidan[feidan_index + 0].reset((myplane.rect.centerx - 66, myplane.rect.centery))
                    feidan[feidan_index + 1].reset((myplane.rect.centerx + 48, myplane.rect.centery))
                    feidan_index = (feidan_index + 2) % FEIDAN_NUM
            """
            #加载扫屏激光
            if not(delay % 300):
                my_lasers[my_lasers_index].reset((0, myplane.rect.top))
                my_lasers_index = (my_lasers_index + 1) % MY_LASERS_NUM

            if sweep:
                for each in my_lasers:               
                    if each.active:
                        each.move()
                        screen.blit(each.image, each.rect)
                        sweep_hit= pygame.sprite.spritecollide(each,enemies,False,pygame.sprite.collide_mask)
                        if sweep_hit:
                            for b in enemies:
                                if b in bigenemies or b in midenemies:
                                    b.hit = True
                                    b.energy -= 5
                                    if b.energy <= 0:
                                        b.active = False
                                elif b in bosses:
                                    b.energy -= 2
                                    if b.energy <= 0:
                                        b.active = False
                                else:
                                    b.active = False
            """

            # 加载子弹
            if not (delay % 10):
                bullet_sound.play()
                if not isinstance(lv, str):
                    if lv == 1:
                        if is_double:
                            bullets = bullet2
                            bullets[bullet2_index + 0].reset((myplane.rect.centerx - 33, myplane.rect.centery))
                            bullets[bullet2_index + 1].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                            bullet2_index = (bullet2_index + 2) % BULLET2_NUM
                        else:
                            bullets = bullet1
                            bullets[bullet1_index].reset(myplane.rect.midtop)
                            bullet1_index = (bullet1_index + 1) % BULLET1_NUM

                    elif lv == 2:
                        if is_double:
                            bullets = bullet4
                            bullets[bullet4_index + 0].reset((myplane.rect.centerx - 33, myplane.rect.centery))
                            bullets[bullet4_index + 1].reset((myplane.rect.centerx - 15, myplane.rect.centery))
                            bullets[bullet4_index + 2].reset((myplane.rect.centerx + 15, myplane.rect.centery))
                            bullets[bullet4_index + 3].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                            bullet4_index = (bullet4_index + 4) % BULLET4_NUM
                        else:
                            bullets = bullet2
                            bullets[bullet2_index + 0].reset((myplane.rect.centerx - 33, myplane.rect.centery))
                            bullets[bullet2_index + 1].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                            bullet2_index = (bullet2_index + 2) % BULLET2_NUM

                    elif lv == 3:
                        if is_double:
                            bullets = bullet5
                            bullets[bullet5_index + 0].reset((myplane.rect.centerx - 34, myplane.rect.centery))
                            bullets[bullet5_index + 1].reset((myplane.rect.centerx - 15, myplane.rect.centery))
                            bullets[bullet5_index + 2].reset(myplane.rect.midtop)
                            bullets[bullet5_index + 3].reset((myplane.rect.centerx + 15, myplane.rect.centery))
                            bullets[bullet5_index + 4].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                            bullet5_index = (bullet5_index + 5) % BULLET5_NUM
                        else:
                            bullets = bullet3
                            bullets[bullet3_index + 0].reset((myplane.rect.centerx - 33, myplane.rect.centery))
                            bullets[bullet3_index + 1].reset(myplane.rect.midtop)
                            bullets[bullet3_index + 2].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                            bullet3_index = (bullet3_index + 3) % BULLET3_NUM

                    elif lv == 4:
                        if is_double:
                            bullets = bullet6
                            bullets[bullet6_index + 0].reset((myplane.rect.centerx - 34, myplane.rect.centery))
                            bullets[bullet6_index + 1].reset((myplane.rect.centerx - 23, myplane.rect.centery))
                            bullets[bullet6_index + 2].reset((myplane.rect.centerx - 10, myplane.rect.centery))
                            bullets[bullet6_index + 3].reset((myplane.rect.centerx + 10, myplane.rect.centery))
                            bullets[bullet6_index + 4].reset((myplane.rect.centerx + 21, myplane.rect.centery))
                            bullets[bullet6_index + 5].reset((myplane.rect.centerx + 32, myplane.rect.centery))
                            bullet6_index = (bullet6_index + 6) % BULLET6_NUM
                        else:
                            bullets = bullet4
                            bullets[bullet4_index + 0].reset((myplane.rect.centerx - 33, myplane.rect.centery))
                            bullets[bullet4_index + 1].reset((myplane.rect.centerx - 15, myplane.rect.centery))
                            bullets[bullet4_index + 2].reset((myplane.rect.centerx + 15, myplane.rect.centery))
                            bullets[bullet4_index + 3].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                            bullet4_index = (bullet4_index + 4) % BULLET4_NUM

                    elif lv == 5:
                        if is_double:
                            bullets = bullet7
                            bullets[bullet7_index + 0].reset((myplane.rect.centerx - 34, myplane.rect.centery))
                            bullets[bullet7_index + 1].reset((myplane.rect.centerx - 23, myplane.rect.centery))
                            bullets[bullet7_index + 2].reset((myplane.rect.centerx - 10, myplane.rect.centery))
                            bullets[bullet7_index + 3].reset(myplane.rect.midtop)
                            bullets[bullet7_index + 4].reset((myplane.rect.centerx + 10, myplane.rect.centery))
                            bullets[bullet7_index + 5].reset((myplane.rect.centerx + 21, myplane.rect.centery))
                            bullets[bullet7_index + 6].reset((myplane.rect.centerx + 32, myplane.rect.centery))
                            bullet7_index = (bullet7_index + 7) % BULLET7_NUM

                        else:
                            bullets = bullet5
                            bullets[bullet5_index + 0].reset((myplane.rect.centerx - 34, myplane.rect.centery))
                            bullets[bullet5_index + 1].reset((myplane.rect.centerx - 15, myplane.rect.centery))
                            bullets[bullet5_index + 2].reset(myplane.rect.midtop)
                            bullets[bullet5_index + 3].reset((myplane.rect.centerx + 15, myplane.rect.centery))
                            bullets[bullet5_index + 4].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                            bullet5_index = (bullet5_index + 5) % BULLET5_NUM

                    elif lv == 6:
                        if is_double:
                            bullets = bullet9
                            bullets[bullet9_index + 0].reset((myplane.rect.centerx - 44, myplane.rect.centery))
                            bullets[bullet9_index + 1].reset((myplane.rect.centerx - 34, myplane.rect.centery))
                            bullets[bullet9_index + 2].reset((myplane.rect.centerx - 23, myplane.rect.centery))
                            bullets[bullet9_index + 3].reset((myplane.rect.centerx - 10, myplane.rect.centery))
                            bullets[bullet9_index + 4].reset(myplane.rect.midtop)
                            bullets[bullet9_index + 5].reset((myplane.rect.centerx + 10, myplane.rect.centery))
                            bullets[bullet9_index + 6].reset((myplane.rect.centerx + 21, myplane.rect.centery))
                            bullets[bullet9_index + 7].reset((myplane.rect.centerx + 32, myplane.rect.centery))
                            bullets[bullet9_index + 8].reset((myplane.rect.centerx + 42, myplane.rect.centery))
                            bullet9_index = (bullet9_index + 9) % BULLET9_NUM
                        else:
                            bullets = bullet7
                            bullets[bullet7_index + 0].reset((myplane.rect.centerx - 34, myplane.rect.centery))
                            bullets[bullet7_index + 1].reset((myplane.rect.centerx - 23, myplane.rect.centery))
                            bullets[bullet7_index + 2].reset((myplane.rect.centerx - 10, myplane.rect.centery))
                            bullets[bullet7_index + 3].reset(myplane.rect.midtop)
                            bullets[bullet7_index + 4].reset((myplane.rect.centerx + 10, myplane.rect.centery))
                            bullets[bullet7_index + 5].reset((myplane.rect.centerx + 21, myplane.rect.centery))
                            bullets[bullet7_index + 6].reset((myplane.rect.centerx + 32, myplane.rect.centery))
                            bullet7_index = (bullet7_index + 7) % BULLET7_NUM
                else:
                    if is_double:
                        bullets = bullet0
                        bullets[bullet0_index + 0].reset((myplane.rect.centerx - 55, myplane.rect.centery))
                        bullets[bullet0_index + 1].reset((myplane.rect.centerx - 45, myplane.rect.centery))
                        bullets[bullet0_index + 2].reset((myplane.rect.centerx - 34, myplane.rect.centery))
                        bullets[bullet0_index + 3].reset((myplane.rect.centerx - 23, myplane.rect.centery))
                        bullets[bullet0_index + 4].reset((myplane.rect.centerx - 10, myplane.rect.centery))
                        bullets[bullet0_index + 5].reset(myplane.rect.midtop)
                        bullets[bullet0_index + 6].reset((myplane.rect.centerx + 10, myplane.rect.centery))
                        bullets[bullet0_index + 7].reset((myplane.rect.centerx + 21, myplane.rect.centery))
                        bullets[bullet0_index + 8].reset((myplane.rect.centerx + 30, myplane.rect.centery))
                        bullets[bullet0_index + 9].reset((myplane.rect.centerx + 41, myplane.rect.centery))
                        bullets[bullet0_index + 10].reset((myplane.rect.centerx + 50, myplane.rect.centery))
                        bullet0_index = (bullet0_index + 11) % BULLET0_NUM
                    else:
                        bullets = bullet8
                        bullets[bullet8_index + 0].reset((myplane.rect.centerx - 45, myplane.rect.centery))
                        bullets[bullet8_index + 1].reset((myplane.rect.centerx - 35, myplane.rect.centery))
                        bullets[bullet8_index + 2].reset((myplane.rect.centerx - 23, myplane.rect.centery))
                        bullets[bullet8_index + 3].reset((myplane.rect.centerx - 10, myplane.rect.centery))
                        bullets[bullet8_index + 4].reset((myplane.rect.centerx + 10, myplane.rect.centery))
                        bullets[bullet8_index + 5].reset((myplane.rect.centerx + 21, myplane.rect.centery))
                        bullets[bullet8_index + 6].reset((myplane.rect.centerx + 32, myplane.rect.centery))
                        bullets[bullet8_index + 7].reset((myplane.rect.centerx + 41, myplane.rect.centery))
                        bullet8_index = (bullet8_index + 8) % BULLET8_NUM
                        # =========================================================
            # 补给（随机奖励生命）
            if _prize_life:
                is_all_life = False
                for each in _prize_life:
                    if each.active:
                        if not delay % 240:
                            switch_image = not switch_image
                        if switch_image:
                            screen.blit(each.image_list[life_index], each.rect)
                            life_index = (life_index + 1) % 2
                        else:
                            screen.blit(each.image_list[life_index], each.rect)
                            life_index = (life_index + 2) % 2

                        each.move()
                        i = pygame.sprite.spritecollide(myplane, _prize_life, False, pygame.sprite.collide_mask)
                        if i:
                            for each in i:
                                each.active = False
                                _prize_life.remove(each)
                                if life_num < 6:
                                    life_num += 1

                    # 未拾取且移动超出边界时释放内存
                    else:
                        _prize_life.remove(each)

            # 补给（随机奖励炸弹）
            if _prize_bomb:
                is_all_bomb = False
                for each in _prize_bomb:
                    if each.active:
                        screen.blit(each.image, each.rect)
                        each.move()
                        i = pygame.sprite.spritecollide(myplane, _prize_bomb, False, pygame.sprite.collide_mask)
                        if i:
                            for each in i:
                                each.active = False
                                _prize_bomb.remove(each)
                                if bomb_num < 6:
                                    bomb_num += 1

                    # 未拾取且移动超出边界时释放内存
                    else:
                        _prize_bomb.remove(each)

            # 补给（固定时间炸弹）
            if supply_bomb.active:
                supply_bomb.move()
                screen.blit(supply_bomb.image, supply_bomb.rect)
                if supply_bomb.rect.top == -10:
                    supply_sound.play()
                    if shields.energy <= 1600:
                        shields.energy += 400
                if pygame.sprite.collide_mask(supply_bomb, myplane):
                    if bomb_num < 6:
                        bomb_num += 1
                    supply_bomb.active = False

            # 补给（随机奖励子弹）
            for each in _prize_bullet:
                if each.active:
                    screen.blit(each.image, each.rect)
                    each.move()
                    i = pygame.sprite.spritecollide(myplane, _prize_bullet, False, pygame.sprite.collide_mask)
                    if i:
                        for each in i:
                            is_double = True
                            pygame.time.set_timer(DOUBLE_BULLET_TIME, 18 * 1000)
                            each.active = False
                            _prize_bullet.remove(each)

                # 未拾取且移动超出边界时释放内存
                else:
                    _prize_bullet.remove(each)

            # 补给（固定时间子弹）
            if supply_bullet.active:
                screen.blit(supply_bullet.image, supply_bullet.rect)
                supply_bullet.move()
                if supply_bullet.rect.top == -10:
                    supply_sound.play()
                    if shields.energy <= 1600:
                        shields.energy += 400
                if pygame.sprite.collide_mask(supply_bullet, myplane):
                    is_double = True
                    pygame.time.set_timer(DOUBLE_BULLET_TIME, 18 * 1000)
                    supply_bullet.active = False

            # =========================================================
            # 敌机尾气
            if boss.rect.top == 0:
                if not delay % 1:
                    boss_bullet[boss_bullet_index].reset((boss.rect.centerx + 22, boss.rect.centery))
                    boss_bullet[boss_bullet_index + 1].reset((boss.rect.centerx - 120, boss.rect.centery))
                    boss_bullet_index = (boss_bullet_index + 2) % BOSS_BULLET_NUM
                for i in boss_bullet:
                    if i.active:
                        i.move()
                        screen.blit(i.image, i.rect)
                        if pygame.sprite.collide_mask(i, myplane):

                            i.active = False
                            my_down.play()
                            life_num -= 1
                            if life_num >= 0:
                                myplane.blink = True
                                is_double = False
                                myplane.reset()
                                pygame.time.set_timer(INVINCIBLE_TIME, 3 * 1000)
                                bomb_num = 3
                            else:
                                myplane.active = False

            # 加载敌机boss子弹
            # 敌机boss子弹与我方碰撞检测
            if boss.rect.top == 0:
                if lv in [1, 2]:
                    boss_bullets = boss_bullet1
                    if not delay % 120:
                        boss_bullet1[boss_bullet1_index].reset((boss.rect.centerx + 62, boss.rect.centery))
                        boss_bullet1[boss_bullet1_index + 1].reset((boss.rect.centerx - 7, boss.rect.centery))
                        boss_bullet1[boss_bullet1_index + 2].reset((boss.rect.centerx - 50, boss.rect.centery))
                        boss_bullet1[boss_bullet1_index + 3].reset((boss.rect.centerx - 80, boss.rect.centery))
                        boss_bullet1_index = (boss_bullet1_index + 4) % BOSS_BULLET1_NUM
                elif lv in [3, 4]:
                    boss_bullets = boss_bullet2
                    if not delay % 130:
                        boss_bullet2[boss_bullet2_index].reset((boss.rect.centerx + 62, boss.rect.centery))
                        boss_bullet2[boss_bullet2_index + 1].reset((boss.rect.centerx - 7, boss.rect.centery))
                        boss_bullet2[boss_bullet2_index + 2].reset((boss.rect.centerx - 50, boss.rect.centery))
                        boss_bullet2[boss_bullet2_index + 3].reset((boss.rect.centerx - 80, boss.rect.centery))
                        boss_bullet2_index = (boss_bullet1_index + 4) % BOSS_BULLET2_NUM

                elif lv in [5, 6]:
                    boss_bullets = boss_bullet3
                    if not delay % 140:
                        boss_bullet3[boss_bullet3_index].reset((boss.rect.centerx + 62, boss.rect.centery))
                        boss_bullet3[boss_bullet3_index + 1].reset((boss.rect.centerx - 5, boss.rect.centery))
                        boss_bullet3[boss_bullet3_index + 2].reset((boss.rect.centerx - 50, boss.rect.centery))
                        boss_bullet3[boss_bullet3_index + 3].reset((boss.rect.centerx - 80, boss.rect.centery))
                        boss_bullet3_index = (boss_bullet1_index + 4) % BOSS_BULLET3_NUM

                if boss_bullets:
                    for i in boss_bullets:
                        if i.active:
                            i.move()
                            screen.blit(i.image, i.rect)

                        if pygame.sprite.collide_mask(i, myplane):
                            if not myplane.invincible:
                                my_down.play()
                                i.active = False
                                life_num -= 1

                                if life_num >= 0:
                                    myplane.blink = True
                                    is_double = False
                                    myplane.reset()
                                    pygame.time.set_timer(INVINCIBLE_TIME, 3 * 1000)
                                    bomb_num = 3
                                else:
                                    myplane.active = False

            # 加载boss激光（直）
            # 检测激光是否击中我方飞机
            # 检测激光是否击中飞机防护罩
            if boss.rect.top == 0 and lv in [3, 4, 5, 6]:
                if not (_delay % 500):
                    if isinstance(lv, int):
                        lasers1[lasers1_index].reset((boss.rect.centerx - 68, boss.rect.centery))
                        lasers1[lasers1_index + 1].reset((boss.rect.centerx + 53, boss.rect.centery))
                        lasers1_index = (lasers1_index + 2) % LASERS1_NUM

                if lasers1:
                    for i in lasers1:
                        if i.active:
                            i.move()
                            screen.blit(i.image, i.rect)
                            if pygame.sprite.collide_mask(i, myplane):
                                if not myplane.invincible:
                                    my_down.play()
                                    life_num -= 1

                                    if life_num >= 0:
                                        myplane.blink = True
                                        is_double = False
                                        myplane.reset()
                                        pygame.time.set_timer(INVINCIBLE_TIME, 3 * 1000)
                                        bomb_num = 3
                                    else:
                                        myplane.active = False

                            if shields.active:
                                if pygame.sprite.collide_mask(i, shields):
                                    shields.hit = True
                                    # hp大于15%按百分比伤害，小于直接秒杀
                                    if _remain > 0.15:
                                        if lv < 3:
                                            shields.energy -= shields.energy * 0.01
                                        elif lv == 3:
                                            shields.energy -= shields.energy * 0.02
                                        elif lv == 4:
                                            shields.energy -= shields.energy * 0.03
                                        elif lv == 5:
                                            shields.energy -= shields.energy * 0.04
                                        else:
                                            shields.energy -= shields.energy * 0.05
                                    else:
                                        shields.energy = 0

                                    if shields.energy <= 0:
                                        shields.active = False
                                        pygame.time.set_timer(INVINCIBLE_TIME, 3 * 1000)
            # 检测飞弹是否击中敌机
            if feidan:
                for i in feidan:
                    if i.active:
                        i.move()
                        screen.blit(i.image, i.rect)
                        enemy_hit = pygame.sprite.spritecollide(i, enemies, False, pygame.sprite.collide_mask)
                        if enemy_hit:
                            i.active = False
                            for b in enemy_hit:
                                if mp < m - 50:
                                    mp += 50
                                if b in bosses:
                                    b.hit = True
                                    b.energy -= 70
                                    if b.energy <= 0:
                                        b.active = False
                                elif b in midenemies or b in bigenemies:
                                    b.hit = True
                                    b.energy -= 50
                                    if b.energy <= 0:
                                        b.active = False
                                else:
                                    b.active = False

            # 检测子弹是否击中敌机
            for i in bullets:
                if i.active:
                    i.move()
                    screen.blit(i.image, i.rect)
                    enemy_hit = pygame.sprite.spritecollide(i, enemies, False, pygame.sprite.collide_mask)
                    if enemy_hit:
                        i.active = False
                        for b in enemy_hit:
                            if mp < m:
                                mp += 1

                            if b in bosses:
                                b.hit = True
                                if i.speed == 10:
                                    b.energy -= 2
                                else:
                                    b.energy -= 1

                                if b.energy <= 0:
                                    b.active = False

                            elif b in midenemies or b in bigenemies:
                                b.hit = True

                                # 子弹伤害值
                                if i.speed == 10:
                                    b.energy -= 2
                                else:
                                    b.energy -= 1

                                if b.energy <= 0:
                                    b.active = False

                            else:
                                b.active = False

            # 双方飞机碰撞检测
            enemies_down = pygame.sprite.spritecollide(myplane, enemies, False, pygame.sprite.collide_mask)
            if enemies_down and (not myplane.invincible):
                my_down.play()
                life_num -= 1
                if life_num >= 0:
                    myplane.blink = True
                    is_double = False
                    myplane.reset()
                    pygame.time.set_timer(INVINCIBLE_TIME, 3 * 1000)
                    bomb_num = 3
                else:
                    myplane.active = False

                for i in enemies_down:
                    if i in bosses:
                        i.energy *= 0.8
                    else:
                        i.active = False

            # 更新关卡boss
            if bosses:
                _delay += 1
                for each in bosses:
                    if each.active:
                        each.move()
                        if each.hit:
                            screen.blit(each.image_hit, each.rect)
                            each.hit = False
                        else:
                            screen.blit(each.image, each.rect)
                        # 绘制血槽
                        pygame.draw.line(screen, BLACK, \
                                         (each.rect.left, each.rect.top + 4), \
                                         (each.rect.right, each.rect.top + 4))
                        # 当生命大于20%显示绿色，否则显示红色
                        energy_remain = each.energy / enemy.Boss.energy
                        if energy_remain > 0.2:
                            energy_color = GREEN
                        else:
                            energy_color = RED
                        pygame.draw.line(screen, energy_color, \
                                         (each.rect.left, each.rect.top + 4), \
                                         (each.rect.left + each.rect.width * energy_remain, \
                                          each.rect.top + 4), 4)

                        if lv in [3, 4, 5, 6]:
                            # 绘制能量
                            pygame.draw.line(screen, BLACK, \
                                             (each.rect.left, each.rect.top + 12), \
                                             (each.rect.right, each.rect.top + 12))
                            # 能量大于60%显示黄色，否则显示红色
                            remain = _delay % 500 / 500
                            if remain > 0.8:
                                color = RED
                            else:
                                color = YELLOW

                            pygame.draw.line(screen, color, \
                                             (each.rect.left, each.rect.top + 12), \
                                             (each.rect.left + each.rect.width * remain, \
                                              each.rect.top + 12), 4)

                    else:
                        if not transform:
                            position = each.rect.center
                            # 原地生成一个随机奖励
                            if not choice(range(lv_dict[5])):
                                prize_bomb = supply.Bomb1(size, position)
                                _prize_bomb.add(prize_bomb)

                            if not choice(range(lv_dict[5])):
                                prize_life = _plane.Life(size, position)
                                _prize_life.add(prize_life)

                            _delay = 0

            # 关卡boss时其他敌机初始待命
            if not is_move:
                for each in enemies:
                    if each not in bosses:
                        each.reset()

            # 更新大敌机
            for each in bigenemies:
                if each.active:
                    if is_move:
                        each.move()
                        if each.hit:
                            screen.blit(each.image_hit, each.rect)
                            each.hit = False
                        else:
                            if switch_image:
                                screen.blit(each.image1, each.rect)
                            else:
                                screen.blit(each.image2, each.rect)

                        # 绘制血槽
                        pygame.draw.line(screen, BLACK, \
                                         (each.rect.left, each.rect.top - 5), \
                                         (each.rect.right, each.rect.top - 5))
                        # 当生命大于20%显示绿色，否则显示红色
                        energy_remain = each.energy / enemy.BigEnemy.energy
                        if energy_remain > 0.2:
                            energy_color = GREEN
                        else:
                            energy_color = RED
                        pygame.draw.line(screen, energy_color, \
                                         (each.rect.left, each.rect.top - 5), \
                                         (each.rect.left + each.rect.width * energy_remain, \
                                          each.rect.top - 5), 2)
                        if each.rect.bottom == -50:
                            enemy3_flying.play(-1)
                        elif each.rect.top == each.size[1] - 110:
                            enemy3_flying.stop()

                else:
                    # 获取大敌机毁灭时的位置
                    position = each.rect.center
                    if not (delay % 3):
                        if big_destroy_index == 0:
                            enemy3_down.play()
                        screen.blit(each.destroy_image[big_destroy_index], each.rect)
                        big_destroy_index = (big_destroy_index + 1) % 6
                        if big_destroy_index == 0:
                            enemy3_flying.stop()
                            score += 100
                            each.reset()
                            # 原地生成一个随机奖励
                            if not choice(range(10)):
                                prize_bomb = supply.Bomb1(size, position)
                                _prize_bomb.add(prize_bomb)
                            if not choice(range(10)):
                                prize_bullet = supply.Bullet1(size, position)
                                _prize_bullet.add(prize_bullet)
                            if not choice(range(20)):
                                prize_life = _plane.Life(size, position)
                                _prize_life.add(prize_life)

            # 更新中敌机
            for each in midenemies:
                if each.active:
                    if is_move:
                        each.move()
                        if each.hit:
                            screen.blit(each.image_hit, each.rect)
                            each.hit = False
                        else:
                            screen.blit(each.image, each.rect)
                        # 绘制血槽
                        pygame.draw.line(screen, BLACK, \
                                         (each.rect.left, each.rect.top - 5), \
                                         (each.rect.right, each.rect.top - 5))
                        # 当生命大于20%显示绿色，否则显示红色
                        energy_remain = each.energy / enemy.MidEnemy.energy
                        if energy_remain > 0.2:
                            energy_color = GREEN
                        else:
                            energy_color = RED
                        pygame.draw.line(screen, energy_color, \
                                         (each.rect.left, each.rect.top - 5), \
                                         (each.rect.left + each.rect.width * energy_remain, \
                                          each.rect.top - 5), 2)
                else:
                    position = each.rect.center
                    if not (delay % 3):
                        if mid_destroy_index == 0:
                            enemy2_down.play()
                        screen.blit(each.destroy_image[mid_destroy_index], each.rect)
                        mid_destroy_index = (mid_destroy_index + 1) % 4
                        if mid_destroy_index == 0:
                            score += 5
                            each.reset()
                            if not choice(range(100)):
                                prize_bomb = supply.Bomb1(size, position)
                                _prize_bomb.add(prize_bomb)
                            if not choice(range(100)):
                                prize_bullet = supply.Bullet1(size, position)
                                _prize_bullet.add(prize_bullet)
                            if not choice(range(200)):
                                prize_life = _plane.Life(size, position)
                                _prize_life.add(prize_life)
            # 更新小敌机
            for each in smallenemies:
                if each.active:
                    if is_move:
                        each.move()
                        screen.blit(each.image, each.rect)
                else:
                    position = each.rect.center
                    if not (delay % 3):
                        if small_destroy_index == 0:
                            enemy1_down.play()
                        screen.blit(each.destroy_image[small_destroy_index], each.rect)
                        small_destroy_index = (small_destroy_index + 1) % 4
                        if small_destroy_index == 0:
                            score += 100
                            each.reset()
                            if not choice(range(1000)):
                                prize_bomb = supply.Bomb1(size, position)
                                _prize_bomb.add(prize_bomb)
                            if not choice(range(1000)):
                                prize_bullet = supply.Bullet1(size, position)
                                _prize_bullet.add(prize_bullet)
                            if not choice(range(2000)):
                                prize_life = _plane.Life(size, position)
                                _prize_life.add(prize_life)
            delay -= 1
            if not delay:
                delay = 1000

        elif life_num < 0:
            screen.fill(background_colour)
            #pygame.mixer.music.stop()
            pygame.mixer.stop()
            enemy.BigEnemy.energy = 40
            enemy.MidEnemy.energy = 10
            enemy.Boss.energy = 200
            if not opened:
                # 稍微延迟下刷新
                pygame.time.delay(1000)
                file = "recode.txt"
                if not os.path.exists(file):
                    with open(file, "w") as g:
                        g.write("0")

                with open(file, "r") as f:
                    recode_score = int(f.read())
                    if score > recode_score:
                        score_best = score_font.render("The best: %s" % str(score), True, BLACK)
                        congratulate = score_font2.render("Congratulations on your record !", True, BLACK)
                        # 刷新记录祝贺
                        is_congratulate = True
                        con_rect = congratulate.get_rect()
                        con_rect.left, con_rect.top = (size[0] - con_rect.width) // 2, \
                                                      (size[1] - con_rect.height) // 2 + 50

                        with open(file, "w") as f:
                            f.write(str(score))
                    else:
                        score_best = score_font.render("The best: %s" % str(recode_score), True, BLACK)

                    score_player = score_font1.render("Your Score:%s" % str(score), True, BLACK)
                    # Game over
                    gameover_image = score_font.render("Game over !", True, BLACK)
                    gameover_image_rect = gameover_image.get_rect()
                    gameover_image_rect.left, gameover_image_rect.top = \
                        (size[0] - gameover_image_rect.width) // 2, \
                        (size[1] - gameover_image_rect.height) // 2

                opened = True

            # 绘制结束界面
            if is_congratulate:
                screen.blit(congratulate, con_rect)
            screen.blit(restart_image, restart_rect)
            screen.blit(stop_image, stop_rect)
            screen.blit(score_best, (20, 20))
            screen.blit(score_player, (20, 80))
            screen.blit(gameover_image, gameover_image_rect)

        # 绘制缓存
        pygame.display.flip()
        clock.tick(60)
        #print(clock.get_fps())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="face controlled game")
    parser.add_argument('-c', '--camera', help="camera index", type=int, default=10)
    parser.add_argument('-d', '--device', help="target device id", type=str)
    #parser.add_argument('-b', '--db_file', help="face database path", required=True)
    parser.add_argument('-b', '--db_file', help="face database path", default="face.db")
    parser.add_argument('-i', '--image_dir', help="import image dir")
    args = parser.parse_args()

    face_det_handle = RockX(RockX.ROCKX_MODULE_FACE_DETECTION, target_device=args.device)
    face_landmark68_handle = RockX(RockX.ROCKX_MODULE_FACE_LANDMARK_68, target_device=args.device)
    face_landmark5_handle = RockX(RockX.ROCKX_MODULE_FACE_LANDMARK_5, target_device=args.device)
    face_recog_handle = RockX(RockX.ROCKX_MODULE_FACE_RECOGNIZE, target_device=args.device)
    face_track_handle = RockX(RockX.ROCKX_MODULE_OBJECT_TRACK, target_device=args.device)
    
    
    try:
        main()
    except SystemExit:
        pass
    except:
        traceback.print_exc()
        pygame.quit()
        input("press any key quit")
    gif = imageio
