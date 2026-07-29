import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from rzd_api import RzdClient

logger = logging.getLogger(__name__)

CAR_TYPE_TRANSLATION = {
    "Compartment": "Купе",
    "Platzkart": "Плацкарт",
    "SV": "СВ",
    "Luxury": "Люкс",
    "Sitting": "Сидячий",
    "Soft": "Мягкий"
}

def _sync_find_stations(query: str) -> List[Dict[str, str]]:
    client = RzdClient()
    try:
        stations = client.find_stations(query)
        result = []
        for st in stations:
            result.append({
                "name": getattr(st, "name", query),
                "code": str(getattr(st, "code", ""))
            })
        return result
    except Exception as e:
        logger.error(f"Error finding stations for query '{query}': {e}")
        return []
    finally:
        client.close()

def _sync_search_tickets(origin_code: str, destination_code: str, date_obj: date) -> List[Any]:
    client = RzdClient()
    try:
        results = client.search_tickets(origin_code, destination_code, date_obj)
        if hasattr(results, "items"):
            return results.items
        elif isinstance(results, list):
            return results
        return []
    except Exception as e:
        logger.error(f"Error searching tickets from {origin_code} to {destination_code} on {date_obj}: {e}")
        raise e
    finally:
        client.close()

def _get_departure_str(item) -> str:
    dep = getattr(item, "departure_time", None) or getattr(item, "departure_date_time", None)
    if not dep and hasattr(item, "raw") and isinstance(item.raw, dict):
        dep = item.raw.get("DepartureDateTime") or item.raw.get("LocalDepartureDateTime")
    return str(dep) if dep else ""

def _get_arrival_str(item) -> str:
    arr = getattr(item, "arrival_time", None) or getattr(item, "arrival_date_time", None)
    if not arr and hasattr(item, "raw") and isinstance(item.raw, dict):
        arr = item.raw.get("ArrivalDateTime") or item.raw.get("LocalArrivalDateTime")
    return str(arr) if arr else ""

def _format_time_only(datetime_str: str) -> str:
    if not datetime_str:
        return ""
    if "T" in datetime_str:
        return datetime_str.split("T")[1][:5]
    if " " in datetime_str:
        return datetime_str.split(" ")[1][:5]
    return datetime_str[:5]

async def find_stations(query: str) -> List[Dict[str, str]]:
    return await asyncio.to_thread(_sync_find_stations, query)

async def get_train_schedule(origin_code: str, destination_code: str, target_date: date) -> List[Dict[str, Any]]:
    try:
        items = await asyncio.to_thread(_sync_search_tickets, origin_code, destination_code, target_date)
    except Exception as e:
        logger.error(f"get_train_schedule failed: {e}")
        return []

    trains_list = []
    for item in items:
        train_no = getattr(item, "display_number", None) or getattr(item, "route_number", None) or getattr(item, "number", "")
        train_name = getattr(item, "train_name", "") or getattr(item, "train_description", "")
        if not train_name and hasattr(item, "raw") and isinstance(item.raw, dict):
            train_name = item.raw.get("TrainName") or item.raw.get("TrainDescription") or ""

        dep_dt = _get_departure_str(item)
        arr_dt = _get_arrival_str(item)

        dep_time = _format_time_only(dep_dt)
        arr_time = _format_time_only(arr_dt)

        trains_list.append({
            "number": str(train_no).upper(),
            "name": str(train_name),
            "departure": dep_time,
            "arrival": arr_time
        })
    return trains_list

async def check_train_tickets_for_date_range(
    origin_code: str,
    destination_code: str,
    date_start: date,
    date_end: date,
    car_type_filter: str = "ANY",
    lower_seats_only: bool = False,
    upper_seats_only: bool = False,
    no_side_seats: bool = False,
    min_seats_count: int = 1,
    train_number_filter: str = ""
) -> List[Dict[str, Any]]:
    all_matching_trains = []
    
    current_d = date_start
    while current_d <= date_end:
        items = await asyncio.to_thread(_sync_search_tickets, origin_code, destination_code, current_d)
        clean_train_filter = train_number_filter.strip().upper()

        for item in items:
            train_no = getattr(item, "display_number", None) or getattr(item, "route_number", None) or getattr(item, "number", "")
            train_no_str = str(train_no).upper()

            if clean_train_filter and clean_train_filter not in train_no_str:
                continue

            train_name = getattr(item, "train_name", "") or getattr(item, "train_description", "Поезд")
            if not train_name and hasattr(item, "raw") and isinstance(item.raw, dict):
                train_name = item.raw.get("TrainName") or item.raw.get("TrainDescription") or "Поезд"

            departure_time = _get_departure_str(item)
            arrival_time = _get_arrival_str(item)
            origin_name = getattr(item, "origin_name", "") or (item.raw.get("OriginStationName") if hasattr(item, "raw") else "")
            dest_name = getattr(item, "destination_name", "") or (item.raw.get("DestinationStationName") if hasattr(item, "raw") else "")

            car_groups = getattr(item, "car_groups", [])
            matched_cars = []

            for car in car_groups:
                c_type = getattr(car, "car_type", "")
                c_type_name = CAR_TYPE_TRANSLATION.get(c_type, getattr(car, "car_type_name", c_type))

                if car_type_filter != "ANY":
                    if car_type_filter.lower() not in c_type.lower() and car_type_filter.lower() not in c_type_name.lower():
                        continue

                total_places = getattr(car, "place_quantity", 0) or getattr(car, "available_places", 0)
                lower_main = getattr(car, "lower_place_quantity", 0)
                lower_side = getattr(car, "lower_side_place_quantity", 0)
                upper_main = getattr(car, "upper_place_quantity", 0)
                upper_side = getattr(car, "upper_side_place_quantity", 0)
                min_price = getattr(car, "min_price", 0.0)

                total_lower = lower_main + lower_side
                total_upper = upper_main + upper_side

                if total_places < min_seats_count:
                    continue

                if lower_seats_only:
                    target_lower = lower_main if no_side_seats else total_lower
                    if target_lower < min_seats_count:
                        continue

                if upper_seats_only:
                    target_upper = upper_main if no_side_seats else total_upper
                    if target_upper < min_seats_count:
                        continue

                if not lower_seats_only and not upper_seats_only and no_side_seats:
                    non_side_total = lower_main + upper_main
                    if non_side_total < min_seats_count:
                        continue

                matched_cars.append({
                    "type": c_type_name,
                    "total_seats": total_places,
                    "lower_seats": total_lower,
                    "upper_seats": total_upper,
                    "min_price": min_price
                })

            if matched_cars:
                all_matching_trains.append({
                    "date": current_d.strftime("%Y-%m-%d"),
                    "train_number": train_no_str,
                    "train_name": train_name,
                    "origin_name": origin_name,
                    "destination_name": dest_name,
                    "departure": departure_time,
                    "arrival": arrival_time,
                    "cars": matched_cars
                })

        current_d += timedelta(days=1)

    return all_matching_trains

async def check_train_tickets(
    origin_code: str,
    destination_code: str,
    target_date: date,
    car_type_filter: str = "ANY",
    lower_seats_only: bool = False,
    upper_seats_only: bool = False,
    no_side_seats: bool = False,
    min_seats_count: int = 1,
    train_number_filter: str = ""
) -> List[Dict[str, Any]]:
    return await check_train_tickets_for_date_range(
        origin_code=origin_code,
        destination_code=destination_code,
        date_start=target_date,
        date_end=target_date,
        car_type_filter=car_type_filter,
        lower_seats_only=lower_seats_only,
        upper_seats_only=upper_seats_only,
        no_side_seats=no_side_seats,
        min_seats_count=min_seats_count,
        train_number_filter=train_number_filter
    )
