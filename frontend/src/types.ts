export interface Item {
  id: number;
  title: string;
  category: string;
  value: number;
  description?: string;
  created_at: string;
}

export interface StatsResponse {
  stats: {
    count: number;
    total_value: number;
    average_value: number;
    status: string;
  };
  external: {
    market_status: string;
    benchmark_sp500: number;
    sentiment_score: number;
  };
}
