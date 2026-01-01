#!/usr/bin/env python3
"""
手机端/采集端主程序
功能：录制视频 + 自动传输 + 触发分析
"""

import os
import time
import subprocess
import requests

class MobileCaptureApp:
    def __init__(self):
        self.recording_dir = "recordings"
        self.server_url = "http://your-server-url.com/api"
        self.analysis_trigger_url = f"{self.server_url}/trigger-analysis"
        
        # 创建录制目录
        os.makedirs(self.recording_dir, exist_ok=True)
    
    def start_recording(self):
        """开始录制视频"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.mp4"
        filepath = os.path.join(self.recording_dir, filename)
        
        print(f"开始录制: {filename}")
        
        # 这里使用ffmpeg模拟录制，实际应用中应使用手机摄像头API
        try:
            # 录制10秒视频作为示例
            subprocess.run([
                "ffmpeg", "-f", "avfoundation", "-framerate", "30", 
                "-video_size", "1280x720", "-i", "0", 
                "-t", "10", "-vcodec", "libx264", filepath
            ], check=True)
            
            print(f"录制完成: {filename}")
            return filepath
        except Exception as e:
            print(f"录制失败: {str(e)}")
            return None
    
    def transfer_video(self, filepath):
        """自动传输视频到服务器"""
        if not filepath or not os.path.exists(filepath):
            print("传输失败：文件不存在")
            return False
        
        print(f"正在传输视频: {filepath}")
        
        try:
            # 模拟文件上传
            files = {'video': open(filepath, 'rb')}
            response = requests.post(f"{self.server_url}/upload", files=files)
            
            if response.status_code == 200:
                print("视频传输成功")
                return True
            else:
                print(f"视频传输失败：{response.status_code}")
                return False
        except Exception as e:
            print(f"视频传输异常: {str(e)}")
            return False
    
    def trigger_analysis(self, video_id):
        """触发服务器端分析"""
        print(f"触发视频分析: {video_id}")
        
        try:
            response = requests.post(self.analysis_trigger_url, json={'video_id': video_id})
            
            if response.status_code == 200:
                print("分析触发成功")
                return True
            else:
                print(f"分析触发失败：{response.status_code}")
                return False
        except Exception as e:
            print(f"分析触发异常: {str(e)}")
            return False
    
    def run(self):
        """运行主程序"""
        print("=== 象棋视频采集端 ===")
        
        # 开始录制
        filepath = self.start_recording()
        
        if filepath:
            # 传输视频
            if self.transfer_video(filepath):
                # 触发分析
                video_id = os.path.basename(filepath).split('.')[0]
                self.trigger_analysis(video_id)

if __name__ == "__main__":
    app = MobileCaptureApp()
    app.run()