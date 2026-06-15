#ifndef __SEGGER_RTT_QUACKQUACK_WRAPPER_H__
#define __SEGGER_RTT_QUACKQUACK_WRAPPER_H__

#if (RM_COMMS_SPI_CFG_EXTRA_LOG==1)

  /**************************************************************************************************
   * Include RTT/SEGGER_RTT.h and stdarg.h for using SEGGER_RTT_printf and variadic arguments 
   * in the DEBUG_INFO macro. In case that RM_COMMS_SPI_CFG_EXTRA_LOG is set to 1.
   **************************************************************************************************/
  #include "RTT/SEGGER_RTT.h"
  #include "stdarg.h"

  /**************************************************************************************************
   * Definition of the wrapper macro that uses SEGGER_RTT_printf to print formatted debug information. 
   **************************************************************************************************/

  #ifndef SEGGER_RTT_DEFAULT_BUFFER_INDEX
    #define SEGGER_RTT_DEFAULT_BUFFER_INDEX   (0U)
  #endif /*SEGGER_RTT_DEFAULT_BUFFER_INDEX*/

  #ifndef QQ_INFO
    #define QQ_INFO(__fmt__, ...)             SEGGER_RTT_printf(                        \
                                                      SEGGER_RTT_DEFAULT_BUFFER_INDEX,  \
                                                      "\n[INFO] "                       \
                                                      __fmt__,                          \
                                                      ##__VA_ARGS__)
  #endif /*QQ_INFO*/

  #ifndef QQ_PRINTF
    #define QQ_PRINTF(__fmt__, ...)          SEGGER_RTT_printf(                         \
                                                      SEGGER_RTT_DEFAULT_BUFFER_INDEX,  \
                                                      __fmt__,                          \
                                                      ##__VA_ARGS__)
  #endif /*QQ_PRINTF*/

#endif /*RM_COMMS_SPI_CFG_EXTRA_LOG*/

#if (!defined(RM_COMMS_SPI_CFG_EXTRA_LOG)) || (RM_COMMS_SPI_CFG_EXTRA_LOG==0)

  /**************************************************************************************************
   * Include stdarg.h for variadic arguments wrapper. 
   * In case that RM_COMMS_SPI_CFG_EXTRA_LOG is set to 0 or not defined.
   **************************************************************************************************/
    #include "stdarg.h"

  /**************************************************************************************************
   * Definition of the wrapper macro that uses variadic arguments to discard debug information. 
   **************************************************************************************************/

  #ifndef QQ_INFO
    #define QQ_INFO(__fmt__, ...)
  #endif /*QQ_INFO*/

  #ifndef QQ_PRINTF
    #define QQ_PRINTF(__fmt__, ...)
  #endif /*QQ_PRINTF*/

#endif /*RM_COMMS_SPI_CFG_EXTRA_LOG*/


#endif /* __SEGGER_RTT_QUACKQUACK_WRAPPER_H__ */
