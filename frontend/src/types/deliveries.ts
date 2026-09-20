import type { Asset, OrderStatus } from "./orders";

export interface DeliverySelection {
  delivery_id: string;
  asset_id: string;
  selected_at: string;
  last_exported_at: string | null;
}

export interface DeliveryState {
  order_id: string;
  order_status: OrderStatus;
  has_open_tasks: boolean;
  items: DeliverySelection[];
  versions: Asset[];
  history: (DeliverySelection & { revoked_at: string | null })[];
}
