import React, { useState } from "react";

import {
  AcSwitch,
  AirVolumn,
  CirculationInside,
  CirculationMode,
  AtmosphereLight,
  BackWindowHeating,
  Cold,
  CirculationOutside,
  Defrost,
  FrontWindshieldHeating,
  EcoSwitch,
  MirrorHeating,
  SeatVentilation,
  SeatHeating,
  ReadingLight,
  SeatMassage,
  SteeringwheelAuto,
  Fragrance,
  SteeringwheelHeating,
  WindFeet,
  WindFace,
  SyncSwitch,
  Switch,
  Plus,
  Minus,
  Car
} from '@/components/icons/icons/index';

import { Button } from '@/components/ui/button';

const icons = [
  { name: 'AcSwitch', Comp: AcSwitch },
  { name: 'EcoSwitch', Comp: EcoSwitch },
  { name: 'SyncSwitch', Comp: SyncSwitch },
  { name: 'AirVolumn', Comp: AirVolumn },
  { name: 'CirculationInside', Comp: CirculationInside },
  { name: 'CirculationMode', Comp: CirculationMode },
  { name: 'AtmosphereLight', Comp: AtmosphereLight },
  { name: 'BackWindowHeating', Comp: BackWindowHeating },
  { name: 'Cold', Comp: Cold },
  { name: 'CirculationOutside', Comp: CirculationOutside },
  { name: 'Defrost', Comp: Defrost },
  { name: 'FrontWindshieldHeating', Comp: FrontWindshieldHeating },
  { name: 'MirrorHeating', Comp: MirrorHeating },
  { name: 'SeatVentilation', Comp: SeatVentilation },
  { name: 'SeatHeating', Comp: SeatHeating },
  { name: 'ReadingLight', Comp: ReadingLight },
  { name: 'SeatMassage', Comp: SeatMassage },
  { name: 'SteeringwheelAuto', Comp: SteeringwheelAuto },
  { name: 'Fragrance', Comp: Fragrance },
  { name: 'SteeringwheelHeating', Comp: SteeringwheelHeating },
  { name: 'WindFeet', Comp: WindFeet },
  { name: 'WindFace', Comp: WindFace },
  { name: 'Switch', Comp: Switch },
  { name: 'Plus', Comp: Plus },
  { name: 'Minus', Comp: Minus },
  { name: 'Car', Comp: Car }
];

const IconComponentCard = () => {
  const [isToggled1, setIsToggled1] = useState(false);

 return (
  <div className="flex flex-col gap-8 items-start mb-10">
    {icons.map(({ name, Comp }) => (
      <div key={name} className="flex gap-4 mb-2">
            <Button
                variant="secondary"
                icon={<Comp />}
                isToggled={isToggled1}
                onClick={() => {setIsToggled1(!isToggled1)}}
            />
            <Button
                variant="activated"
                icon={<Comp />}
                isToggled={isToggled1}
                onClick={() => {setIsToggled1(!isToggled1)}}
            >
                {name}
            </Button>
      </div>
    ))}
    <Button
        variant="secondary"
        icon={<Plus />}
        className="w-[388px]! h-[388px] [&_svg]:h-[180px]"
    />
  </div>
 )
};

export default IconComponentCard;