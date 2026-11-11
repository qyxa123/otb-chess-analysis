#!/usr/bin/env python3
"""
Stockfish分析模块
功能：使用Stockfish引擎分析PGN文件，生成分析结果
"""

import chess.engine
import chess.pgn
from otbreview.pipeline.analyze import find_stockfish, _extract_eval
from self_analysis import parse_pgn_text

class StockfishAnalyzer:
    def __init__(self, stockfish_path=None):
        self.stockfish_path = stockfish_path or find_stockfish()
        self.depth = 20
    
    def analyze_pgn(self, pgn_content):
        """分析PGN文件，生成评估结果"""
        print("开始使用Stockfish分析棋局")
        
        try:
            # 解析PGN
            game = parse_pgn_text(pgn_content)
            if self.stockfish_path is None:
                raise RuntimeError("找不到Stockfish，请安装或设置 STOCKFISH_PATH。")
            
            # 设置Stockfish引擎
            with chess.engine.SimpleEngine.popen_uci(self.stockfish_path) as engine:
                board = game.board()
                analysis_results = []
                
                # 遍历每一步棋
                for move in game.mainline_moves():
                    # 分析当前局面
                    info = engine.analyse(board, chess.engine.Limit(depth=self.depth))
                    
                    # 获取评估值
                    evaluation = self._format_evaluation(info["score"], board.turn)
                    
                    analysis_results.append({
                        "move": board.san(move),
                        "fen": board.fen(),
                        "evaluation": evaluation,
                        "depth": info.get("depth", self.depth)
                    })
                    
                    # 执行走棋
                    board.push(move)
                
                # 分析最终局面
                info = engine.analyse(board, chess.engine.Limit(depth=self.depth))
                evaluation = self._format_evaluation(info["score"], board.turn)
                
                analysis_results.append({
                    "move": "终局",
                    "fen": board.fen(),
                    "evaluation": evaluation,
                    "depth": info.get("depth", self.depth)
                })
                
            print("分析完成")
            return analysis_results
            
        except Exception as e:
            print(f"分析失败: {str(e)}")
            return None

    @staticmethod
    def _format_evaluation(score, turn):
        data = _extract_eval(score, turn)
        if data['mate'] is not None:
            return f"#{'+' if data['cp'] > 0 else '-'}{abs(data['mate'])}"
        return f"{data['cp'] / 100:.2f}"
    
    def generate_analysis_report(self, analysis_results):
        """生成分析报告"""
        if not analysis_results:
            return ""
        
        report = "# 棋局分析报告\n\n"
        
        for i, result in enumerate(analysis_results):
            if i < len(analysis_results) - 1:  # 不是终局
                report += f"## 第{i+1}步: {result['move']}\n"
            else:
                report += "## 终局局面\n"
            
            report += f"- 评估值: {result['evaluation']}\n"
            report += f"- 分析深度: {result['depth']}\n"
            report += f"- FEN: {result['fen']}\n\n"
        
        return report
