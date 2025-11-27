class ImpactAnalyzer:
    @staticmethod
    def calculate_score(pagerank_score, delay_minutes):
        """
        核心公式：
        Impact = PageRank权重 * 延误时间
        """
        # 放大系数 1000 是为了让数字好看点
        return pagerank_score * delay_minutes * 1000

    @staticmethod
    def get_color(impact_score):
        """根据影响程度返回颜色"""
        if impact_score > 50: return "red"  # 严重
        if impact_score > 10: return "orange"  # 中等
        if impact_score > 0: return "green"  # 轻微
        return "blue"  # 无延误