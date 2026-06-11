alter table market_model_monthly_stats
  drop constraint if exists market_model_monthly_stats_market_model_id_month_county_municipality_key;

alter table market_model_monthly_stats
  add constraint market_model_monthly_stats_market_model_id_month_county_municipality_key
  unique nulls not distinct (market_model_id, month, county, municipality);
