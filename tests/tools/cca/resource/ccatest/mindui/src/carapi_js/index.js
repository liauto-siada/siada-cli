// 从本地源文件中导入需要暴露的接口
import callbackManager from './callbackManager.js';
import { get_seat_massage_control, get_defrost_defogging_control, get_front_hvac_system, get_hot_stone_massage_system, get_hvac_general_control, get_interior_lighting_system, get_rear_hvac_control, get_rear_seat_heating, get_seat_massage_mode, get_seat_ventilation_system, get_steering_wheel_seat_heating, get_vehicle_environment_monitoring, get_vehicle_fragrance_system, getCarSpeed, getCarGearShift, getNoaRatio, getMileage, get_vehicle_refrigerator_status, get_charging_information, get_ambient_light_information, get_driving_information, get_vehicle_driving_status, get_bind_trip, get_navigation_information, get_perfume_information, triggerGetForType } from './stateGetters.js';
import { setCarValue, set_seat_ventilation_system, set_seat_heating, set_vehicle_driving_control, set_vehicle_fragrance_system, set_interior_lighting_system, set_vehicle_refrigerator_control, set_seat_massage_control, set_hvac_general_control, set_defrost_defogging_control, set_front_hvac_system, set_steering_wheel_seat_heating, set_rear_hvac_control, set_ambient_light_control, setMassageMode, set_charging_control, set_rear_seat_heating, set_seat_massage_mode } from './stateSetters.js';
import { getHttpData, getHttpDataAsync } from './httpGetter.js';
import { GetWeatherInfo } from './CloudAPI/WeatherAPI.ts';
import { GetAlmanacInfo } from './CloudAPI/AlmanacAPI.ts';
import { GetCalendarInfo } from './CloudAPI/CalendarAPI.ts';
import { GetExchangeRateInfo } from './CloudAPI/ExchangeRateAPI.ts';
import { GetHoroscopeInfo } from './CloudAPI/HoroscopeAPI.ts';
import { GetStockInfo } from './CloudAPI/StockAPI.ts';
import { GetTrafficRestrictionInfo } from './CloudAPI/TrafficRestrictionAPI.ts';
import { GetWordInfo } from './CloudAPI/WordAPI.ts';
import { GetPoetryInfo } from './CloudAPI/PoetryAPI.ts';
import { mockData, getMockData } from './carApiGetter.js';
import { registerListener } from './utils.js';

// 将所有接口统一导出，供打包工具使用
export {
    callbackManager,
    get_seat_massage_control,
    get_defrost_defogging_control,
    get_front_hvac_system,
    get_hot_stone_massage_system,
    get_hvac_general_control,
    get_interior_lighting_system,
    get_rear_hvac_control,
    get_rear_seat_heating,
    get_seat_massage_mode,
    get_seat_ventilation_system,
    get_steering_wheel_seat_heating,
    get_vehicle_environment_monitoring,
    get_vehicle_fragrance_system,
    GetWeatherInfo,
    GetAlmanacInfo,
    GetCalendarInfo,
    GetExchangeRateInfo,
    GetHoroscopeInfo,
    GetStockInfo,
    GetTrafficRestrictionInfo,
    GetWordInfo,
    GetPoetryInfo,
    mockData,
    getCarSpeed,
    getCarGearShift,
    getNoaRatio,
    getMileage,
    setCarValue,
    set_seat_ventilation_system,
    set_seat_heating,
    set_vehicle_driving_control,
    set_vehicle_fragrance_system,
    set_interior_lighting_system,
    set_vehicle_refrigerator_control,
    set_seat_massage_control,
    get_vehicle_refrigerator_status,
    get_charging_information,
    get_ambient_light_information,
    get_driving_information,
    get_vehicle_driving_status,
    get_bind_trip,
    set_hvac_general_control,
    set_defrost_defogging_control,
    set_front_hvac_system,
    set_steering_wheel_seat_heating,
    set_rear_hvac_control,
    get_navigation_information,
    get_perfume_information,
    set_ambient_light_control,
    setMassageMode,
    registerListener,
    set_charging_control,
    set_rear_seat_heating,
    set_seat_massage_mode,

    getHttpData,
    getHttpDataAsync,

    triggerGetForType,
};