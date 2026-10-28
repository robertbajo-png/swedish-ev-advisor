-- Repair existing deployments whose enum predates the approved dealer contract.
-- No rows, views, policies or privileges are changed.
alter type public.source_type add value if not exists 'authorized_dealer_model_page';
alter type public.source_type add value if not exists 'authorized_dealer_stock_page';
